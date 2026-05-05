from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from patchpilot.agents import BaseAgent, MockAgent, _detect_backend_issue, _infer_files, _resolve_executable
from patchpilot.cli import (
    _require_existing_directory,
    _require_existing_file,
    bundled_demo_repo,
)
from patchpilot.models import AgentResponse, AgentRole
from patchpilot.workflow import AgentOrchestrator


class StaticAgent(BaseAgent):
    def __init__(self, response: AgentResponse) -> None:
        super().__init__(response.agent_name)
        self.response = response

    async def run(self, request) -> AgentResponse:
        return self.response


class WorkflowTests(unittest.TestCase):
    def test_mock_workflow_generates_expected_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            (repo / "README.md").write_text("# Example repo\n", encoding="utf-8")
            src_dir = repo / "src"
            src_dir.mkdir()
            (src_dir / "app.py").write_text("print('hello')\n", encoding="utf-8")

            output_root = Path(tmp) / "runs"
            orchestrator = AgentOrchestrator(
                codex_agent=MockAgent("codex"),
                claude_agent=MockAgent("claude"),
                output_root=output_root,
                max_iterations=2,
                approval_threshold=8,
            )

            result = asyncio.run(
                orchestrator.run(
                    task="Add structured logging to the handler layer",
                    repo_path=repo,
                )
            )

            self.assertTrue(result.output_dir.exists())
            self.assertTrue((result.output_dir / "03_supervisor_plan.md").exists())
            self.assertTrue((result.output_dir / "99_final_summary.md").exists())
            self.assertTrue(result.approved)
            summary = (result.output_dir / "99_final_summary.md").read_text(encoding="utf-8")
            self.assertIn("Approved: yes", summary)

    def test_high_risk_task_uses_risk_mitigation_branch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            (repo / "README.md").write_text("# Risky repo\n", encoding="utf-8")

            orchestrator = AgentOrchestrator(
                codex_agent=MockAgent("codex"),
                claude_agent=MockAgent("claude"),
                output_root=Path(tmp) / "runs",
                max_iterations=2,
                approval_threshold=8,
            )

            result = asyncio.run(
                orchestrator.run(
                    task="Harden payment auth migration before release",
                    repo_path=repo,
                )
            )

            self.assertEqual(result.branch, "risk_mitigation")
            self.assertTrue((result.output_dir / "04_risk_mitigation_brief.md").exists())

    def test_bundled_demo_repo_exists(self) -> None:
        repo = bundled_demo_repo()
        self.assertTrue(repo.exists())
        self.assertTrue((repo / "README.md").exists())
        self.assertTrue((repo / "package.json").exists())
        self.assertTrue((repo / "tsconfig.json").exists())
        self.assertTrue((repo / "src" / "app.ts").exists())

    def test_missing_repository_path_raises_clear_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "Repository path does not exist"):
            _require_existing_directory(
                Path("/path/to/repository"),
                label="Repository path",
                hint="Replace placeholder values like `/path/to/repository` with `.` or a real local path.",
            )

    def test_missing_config_path_raises_clear_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "Agent config does not exist"):
            _require_existing_file(
                Path("missing-agent-config.json"),
                label="Agent config",
                hint="Use a real JSON path such as `examples/agents.example.json`.",
            )

    def test_resolve_executable_uses_absolute_path_when_available(self) -> None:
        resolved = _resolve_executable(["python3", "--version"])
        self.assertTrue(Path(resolved[0]).is_absolute())
        self.assertEqual(resolved[1:], ["--version"])

    def test_infer_files_extracts_clean_paths_from_snapshot(self) -> None:
        files = _infer_files("- `README.md`\n- `src/app.ts`\n### `tests/app.test.ts`")
        self.assertEqual(files[:3], ["README.md", "src/app.ts", "tests/app.test.ts"])

    def test_detect_backend_issue_recognizes_claude_login_problem(self) -> None:
        issue = _detect_backend_issue(
            "claude",
            '{"type":"result","is_error":true,"result":"Not logged in · Please run /login"}',
            1,
        )
        self.assertIsNotNone(issue)
        assert issue is not None
        self.assertEqual(issue["code"], "claude-auth-required")

    def test_workflow_stops_early_when_real_backends_are_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            (repo / "README.md").write_text("# Example repo\n", encoding="utf-8")

            codex_response = AgentResponse(
                agent_name="codex",
                role=AgentRole.PLANNER,
                stage="parallel-discovery",
                summary="Codex unavailable.",
                details="Permission denied.",
                file_suggestions=[],
                quality_score=0,
                risk_score=10,
                needs_follow_up=True,
                backend_issue="Codex CLI could not start.",
                next_step_hint="Use --ephemeral.",
                raw_output="permission denied",
                metadata={"backend": "command", "returncode": 1},
            )
            claude_response = AgentResponse(
                agent_name="claude",
                role=AgentRole.REVIEWER,
                stage="parallel-review",
                summary="Claude unavailable.",
                details="Not logged in.",
                file_suggestions=[],
                quality_score=0,
                risk_score=10,
                needs_follow_up=True,
                backend_issue="Claude Code is not authenticated.",
                next_step_hint="Run claude auth status.",
                raw_output="not logged in",
                metadata={"backend": "command", "returncode": 1},
            )

            orchestrator = AgentOrchestrator(
                codex_agent=StaticAgent(codex_response),
                claude_agent=StaticAgent(claude_response),
                output_root=Path(tmp) / "runs",
            )

            result = asyncio.run(
                orchestrator.run(
                    task="Migrate the project from SQLite to Postgres",
                    repo_path=repo,
                )
            )

            self.assertEqual(result.branch, "blocked")
            self.assertEqual(result.iterations, 0)
            self.assertTrue(result.backend_issues)
            self.assertTrue((result.output_dir / "03_backend_diagnostics.md").exists())
            self.assertFalse((result.output_dir / "03_supervisor_plan.md").exists())


if __name__ == "__main__":
    unittest.main()
