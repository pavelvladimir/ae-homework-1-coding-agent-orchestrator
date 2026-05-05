from __future__ import annotations

from copy import deepcopy

from patchpilot.models import AgentRequest


ROLE_GUIDANCE = {
    "planner": (
        "You are the planning side of a coding agent. Break the task into the smallest safe "
        "implementation steps and call out acceptance criteria."
    ),
    "implementer": (
        "You are the implementation side of a coding agent. Produce a concrete execution brief, "
        "ordered code changes, and the checks needed before merging."
    ),
    "reviewer": (
        "You are the review side of a coding agent. Look for regressions, edge cases, missing "
        "tests, rollout risk, and things that would block approval."
    ),
    "supervisor": (
        "You are the orchestration supervisor. Merge parallel findings into one actionable plan."
    ),
}


JSON_CONTRACT = """Return valid JSON with exactly these keys:
{
  "summary": "short paragraph",
  "details": "multi-line markdown-friendly text",
  "file_suggestions": ["path/one.py", "path/two.md"],
  "quality_score": 0,
  "risk_score": 0,
  "needs_follow_up": false
}

Rules:
- Use integer scores from 0 to 10.
- Do not wrap the JSON in markdown fences.
- Keep file paths relative to the repository root.
"""


AGENT_RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "summary": {"type": "string"},
        "details": {"type": "string"},
        "file_suggestions": {
            "type": "array",
            "items": {"type": "string"},
        },
        "quality_score": {
            "type": "integer",
            "minimum": 0,
            "maximum": 10,
        },
        "risk_score": {
            "type": "integer",
            "minimum": 0,
            "maximum": 10,
        },
        "needs_follow_up": {"type": "boolean"},
    },
    "required": [
        "summary",
        "details",
        "file_suggestions",
        "quality_score",
        "risk_score",
        "needs_follow_up",
    ],
}


def build_agent_prompt(request: AgentRequest) -> str:
    prior_messages = "\n".join(f"- {item}" for item in request.prior_messages) or "- None"
    constraints = "\n".join(f"- {item}" for item in request.constraints) or "- None"
    role_guidance = ROLE_GUIDANCE[request.role.value]

    return (
        f"{role_guidance}\n\n"
        f"Stage: {request.stage}\n"
        f"Iteration: {request.iteration}\n"
        f"Repository path: {request.repo_path}\n"
        f"Task: {request.task}\n\n"
        "Previous agent outputs:\n"
        f"{prior_messages}\n\n"
        "Constraints:\n"
        f"{constraints}\n\n"
        "Repository context:\n"
        f"{request.context}\n\n"
        f"{JSON_CONTRACT}"
    )


def build_agent_response_schema() -> dict[str, object]:
    return deepcopy(AGENT_RESPONSE_SCHEMA)
