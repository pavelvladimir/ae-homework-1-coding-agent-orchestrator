from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class AgentRole(str, Enum):
    PLANNER = "planner"
    IMPLEMENTER = "implementer"
    REVIEWER = "reviewer"
    SUPERVISOR = "supervisor"


@dataclass(slots=True)
class AgentRequest:
    task: str
    repo_path: Path
    stage: str
    role: AgentRole
    context: str
    prior_messages: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    iteration: int = 0

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["repo_path"] = str(self.repo_path)
        payload["role"] = self.role.value
        return payload


@dataclass(slots=True)
class AgentResponse:
    agent_name: str
    role: AgentRole
    stage: str
    summary: str
    details: str
    file_suggestions: list[str]
    quality_score: int
    risk_score: int
    needs_follow_up: bool
    raw_output: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["role"] = self.role.value
        return payload

    def as_markdown(self) -> str:
        file_lines = "\n".join(f"- `{item}`" for item in self.file_suggestions) or "- None"
        meta_lines = "\n".join(
            f"- `{key}`: {value}" for key, value in sorted(self.metadata.items())
        ) or "- None"
        return (
            f"# {self.agent_name} / {self.stage}\n\n"
            f"## Summary\n{self.summary}\n\n"
            f"## Details\n{self.details}\n\n"
            f"## Suggested files\n{file_lines}\n\n"
            f"## Scores\n"
            f"- Quality: {self.quality_score}/10\n"
            f"- Risk: {self.risk_score}/10\n"
            f"- Needs follow-up: {'yes' if self.needs_follow_up else 'no'}\n\n"
            f"## Metadata\n{meta_lines}\n"
        )


@dataclass(slots=True)
class SupervisorPlan:
    branch: str
    summary: str
    rationale: str
    next_step: str
    acceptance_criteria: list[str]
    open_risks: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def as_markdown(self) -> str:
        criteria_lines = "\n".join(f"- {item}" for item in self.acceptance_criteria) or "- None"
        risk_lines = "\n".join(f"- {item}" for item in self.open_risks) or "- None"
        return (
            "# Supervisor plan\n\n"
            f"## Branch\n`{self.branch}`\n\n"
            f"## Summary\n{self.summary}\n\n"
            f"## Rationale\n{self.rationale}\n\n"
            f"## Next step\n{self.next_step}\n\n"
            f"## Acceptance criteria\n{criteria_lines}\n\n"
            f"## Open risks\n{risk_lines}\n"
        )


@dataclass(slots=True)
class WorkflowResult:
    output_dir: Path
    approved: bool
    iterations: int
    branch: str
    final_summary: str
    manifest: list[str]
