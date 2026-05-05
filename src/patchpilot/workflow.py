from __future__ import annotations

import asyncio
from pathlib import Path

from patchpilot.agents import BaseAgent
from patchpilot.artifacts import ArtifactWriter
from patchpilot.models import AgentRequest, AgentRole, SupervisorPlan, WorkflowResult
from patchpilot.repo_context import build_repo_snapshot


class AgentOrchestrator:
    def __init__(
        self,
        codex_agent: BaseAgent,
        claude_agent: BaseAgent,
        *,
        output_root: Path,
        max_iterations: int = 2,
        approval_threshold: int = 8,
    ) -> None:
        self.codex_agent = codex_agent
        self.claude_agent = claude_agent
        self.output_root = output_root
        self.max_iterations = max_iterations
        self.approval_threshold = approval_threshold

    async def run(self, task: str, repo_path: Path) -> WorkflowResult:
        repo_path = repo_path.resolve()
        snapshot = build_repo_snapshot(repo_path)
        writer = ArtifactWriter(self.output_root, task)

        writer.write_text(
            "00_intake.md",
            (
                "# Intake\n\n"
                f"## Task\n{task}\n\n"
                f"## Repository\n`{repo_path}`\n\n"
                f"## Approval threshold\n{self.approval_threshold}/10\n\n"
                f"{snapshot}"
            ),
        )

        parallel_codex_request = AgentRequest(
            task=task,
            repo_path=repo_path,
            stage="parallel-discovery",
            role=AgentRole.PLANNER,
            context=snapshot,
            constraints=[
                "Prefer the smallest safe change surface.",
                "List testable acceptance criteria.",
            ],
        )
        parallel_claude_request = AgentRequest(
            task=task,
            repo_path=repo_path,
            stage="parallel-review",
            role=AgentRole.REVIEWER,
            context=snapshot,
            constraints=[
                "Prioritize review risks, regressions, and missing tests.",
                "Call out rollout or migration concerns early.",
            ],
        )

        codex_discovery, claude_review = await asyncio.gather(
            self.codex_agent.run(parallel_codex_request),
            self.claude_agent.run(parallel_claude_request),
        )
        writer.write_agent_response("01_codex_parallel_discovery", codex_discovery)
        writer.write_agent_response("02_claude_parallel_review", claude_review)

        supervisor_plan = self._build_supervisor_plan(task, codex_discovery, claude_review)
        writer.write_text("03_supervisor_plan.md", supervisor_plan.as_markdown())
        writer.write_json("03_supervisor_plan.json", supervisor_plan.to_dict())

        implementation_stage = (
            "risk-mitigation-brief"
            if supervisor_plan.branch == "risk_mitigation"
            else "implementation-brief"
        )
        implementation_request = AgentRequest(
            task=task,
            repo_path=repo_path,
            stage=implementation_stage,
            role=AgentRole.IMPLEMENTER,
            context=snapshot,
            prior_messages=[
                codex_discovery.summary,
                claude_review.summary,
                supervisor_plan.summary,
                supervisor_plan.next_step,
            ],
            constraints=[
                "Use the supervisor branch and acceptance criteria.",
                "Make the output concrete enough for a developer handoff.",
            ],
        )
        implementation = await self.codex_agent.run(implementation_request)

        implementation_stem = (
            "04_risk_mitigation_brief"
            if supervisor_plan.branch == "risk_mitigation"
            else "04_implementation_brief"
        )
        writer.write_agent_response(implementation_stem, implementation)

        approved = False
        final_review = None
        review_rounds = 0
        for review_round in range(1, self.max_iterations + 1):
            review_rounds = review_round
            review_request = AgentRequest(
                task=task,
                repo_path=repo_path,
                stage=f"review-round-{review_round}",
                role=AgentRole.REVIEWER,
                context=snapshot,
                prior_messages=[
                    supervisor_plan.summary,
                    implementation.summary,
                    implementation.details,
                ],
                constraints=[
                    f"Approve only if quality is at least {self.approval_threshold}/10.",
                    "Focus on missing tests, risk, and clarity of the implementation brief.",
                ],
                iteration=review_round,
            )
            final_review = await self.claude_agent.run(review_request)
            writer.write_agent_response(f"0{4 + review_round}_review_round_{review_round}", final_review)

            if (
                final_review.quality_score >= self.approval_threshold
                and not final_review.needs_follow_up
            ):
                approved = True
                break

            if review_round == self.max_iterations:
                break

            repair_request = AgentRequest(
                task=task,
                repo_path=repo_path,
                stage=f"repair-round-{review_round}",
                role=AgentRole.IMPLEMENTER,
                context=snapshot,
                prior_messages=[
                    supervisor_plan.summary,
                    implementation.details,
                    final_review.details,
                ],
                constraints=[
                    "Address the reviewer findings directly.",
                    "Keep the patch plan small and testable.",
                ],
                iteration=review_round,
            )
            implementation = await self.codex_agent.run(repair_request)
            writer.write_agent_response(
                f"0{5 + review_round}_repair_round_{review_round}",
                implementation,
            )

        final_summary = self._build_final_summary(
            task=task,
            repo_path=repo_path,
            plan=supervisor_plan,
            approved=approved,
            review_rounds=review_rounds,
            final_review=final_review.summary if final_review else "No review output.",
        )
        writer.write_text("99_final_summary.md", final_summary)
        writer.write_json("manifest.json", {"files": writer.manifest})

        return WorkflowResult(
            output_dir=writer.output_dir,
            approved=approved,
            iterations=review_rounds,
            branch=supervisor_plan.branch,
            final_summary=final_summary,
            manifest=list(writer.manifest),
        )

    def _build_supervisor_plan(self, task: str, codex_discovery, claude_review) -> SupervisorPlan:
        branch = "risk_mitigation" if claude_review.risk_score >= 8 else "implementation"
        summary = (
            "Start with a risk-mitigation pass before coding the main change."
            if branch == "risk_mitigation"
            else "Proceed with the normal implementation path and keep the change set narrow."
        )
        rationale = (
            f"Codex proposed a build-first approach while Claude reported risk {claude_review.risk_score}/10. "
            "The supervisor keeps both views: move forward, but only with explicit acceptance criteria."
        )
        next_step = (
            "Produce a mitigation-first brief with rollback notes, targeted tests, and staged rollout guidance."
            if branch == "risk_mitigation"
            else "Produce an implementation brief with concrete file targets, tests, and validation steps."
        )
        acceptance_criteria = [
            "The artifact names and task flow stay easy to present during the demo.",
            "A developer can understand the next coding step without re-reading the full task.",
            "The final packet includes at least one explicit verification step.",
        ]
        if branch == "risk_mitigation":
            acceptance_criteria.append("The plan includes rollback and staged rollout notes.")
        else:
            acceptance_criteria.append("The plan identifies the smallest safe code change surface.")

        open_risks = [
            "Review findings may still require another repair loop.",
            "Large repositories may need a richer snapshot strategy for production usage.",
        ]
        if claude_review.risk_score >= 8:
            open_risks.append("The task includes high-risk keywords and should be rolled out carefully.")

        return SupervisorPlan(
            branch=branch,
            summary=summary,
            rationale=rationale,
            next_step=next_step,
            acceptance_criteria=acceptance_criteria,
            open_risks=open_risks,
        )

    def _build_final_summary(
        self,
        *,
        task: str,
        repo_path: Path,
        plan: SupervisorPlan,
        approved: bool,
        review_rounds: int,
        final_review: str,
    ) -> str:
        return (
            "# Final summary\n\n"
            f"- Task: {task}\n"
            f"- Repository: `{repo_path}`\n"
            f"- Branch: `{plan.branch}`\n"
            f"- Approved: {'yes' if approved else 'no'}\n"
            f"- Review rounds: {review_rounds}\n\n"
            "## Final reviewer signal\n"
            f"{final_review}\n\n"
            "## What this run produced\n"
            "- Parallel discovery from two agent roles\n"
            "- A supervisor-selected branch\n"
            "- An implementation brief\n"
            "- At least one review decision\n"
        )
