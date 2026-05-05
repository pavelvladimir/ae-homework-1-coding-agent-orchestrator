from __future__ import annotations

import abc
import asyncio
import json
import shlex
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from patchpilot.models import AgentRequest, AgentResponse, AgentRole
from patchpilot.prompts import build_agent_prompt


class BaseAgent(abc.ABC):
    def __init__(self, name: str) -> None:
        self.name = name

    @abc.abstractmethod
    async def run(self, request: AgentRequest) -> AgentResponse:
        raise NotImplementedError


class MockAgent(BaseAgent):
    async def run(self, request: AgentRequest) -> AgentResponse:
        await asyncio.sleep(0)
        file_suggestions = _infer_files(request.context)
        risk_score = _estimate_risk(request.task)

        if request.role is AgentRole.PLANNER:
            summary = "Parallel discovery prepared a safe decomposition of the repository task."
            details = (
                "1. Inspect the existing repository context.\n"
                "2. Map the smallest change surface before editing code.\n"
                "3. Prepare acceptance criteria and a rollback-friendly order of work.\n"
                "4. Hand the execution brief to the implementation pass."
            )
            quality_score = 7
            needs_follow_up = False
        elif request.role is AgentRole.IMPLEMENTER:
            repaired = "repair" in request.stage or "risk-mitigation" in request.stage
            summary = (
                "Implementation brief updated to address reviewer feedback."
                if repaired
                else "Implementation brief prepared for the first coding pass."
            )
            details = (
                f"Focus files: {', '.join(file_suggestions[:3]) or 'repository root'}.\n\n"
                "Planned execution order:\n"
                "1. Update the smallest possible set of files.\n"
                "2. Add or extend tests around the risky behavior.\n"
                "3. Verify the workflow output and keep the patch easy to review.\n"
                "4. Include follow-up notes for the reviewer."
            )
            quality_score = 7 + min(request.iteration, 2)
            needs_follow_up = False
        else:
            first_review = request.iteration <= 1 and "review" in request.stage
            summary = (
                "Independent review highlighted the main regression risks and the missing checks."
                if "parallel" in request.stage
                else "Review round completed against the current implementation brief."
            )
            details = (
                "Primary review notes:\n"
                "- Check the happy path and one failure path.\n"
                "- Verify that the edited files stay small and easy to test.\n"
                "- Confirm rollback steps for the riskiest behavior.\n"
                "- Reject the plan if it still lacks targeted tests."
            )
            quality_score = 7 if first_review else 8 + min(request.iteration - 2, 1)
            needs_follow_up = quality_score < 8

        return AgentResponse(
            agent_name=self.name,
            role=request.role,
            stage=request.stage,
            summary=summary,
            details=details,
            file_suggestions=file_suggestions,
            quality_score=quality_score,
            risk_score=risk_score,
            needs_follow_up=needs_follow_up,
            raw_output="mock",
            metadata={"backend": "mock", "iteration": request.iteration},
        )


class CommandTemplateAgent(BaseAgent):
    def __init__(
        self,
        name: str,
        command: list[str] | str,
        *,
        timeout_seconds: int = 180,
    ) -> None:
        super().__init__(name)
        self.command = command
        self.timeout_seconds = timeout_seconds

    async def run(self, request: AgentRequest) -> AgentResponse:
        prompt = build_agent_prompt(request)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".txt",
            delete=False,
        ) as handle:
            handle.write(prompt)
            prompt_path = Path(handle.name)

        command = self._format_command(request=request, prompt_path=prompt_path)
        completed = await asyncio.to_thread(
            subprocess.run,
            command,
            cwd=str(request.repo_path),
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
            check=False,
        )

        stdout = completed.stdout.strip()
        stderr = completed.stderr.strip()
        raw_output = stdout or stderr
        if completed.returncode != 0 and not raw_output:
            raw_output = f"Agent exited with code {completed.returncode}"

        payload = _parse_agent_output(raw_output)
        return AgentResponse(
            agent_name=self.name,
            role=request.role,
            stage=request.stage,
            summary=payload.get("summary", "No summary returned."),
            details=payload.get("details", raw_output or "No details returned."),
            file_suggestions=_ensure_string_list(payload.get("file_suggestions")),
            quality_score=_normalize_score(payload.get("quality_score"), default=5),
            risk_score=_normalize_score(payload.get("risk_score"), default=5),
            needs_follow_up=bool(payload.get("needs_follow_up", completed.returncode != 0)),
            raw_output=raw_output,
            metadata={
                "backend": "command",
                "returncode": completed.returncode,
                "stderr_present": bool(stderr),
            },
        )

    def _format_command(self, *, request: AgentRequest, prompt_path: Path) -> list[str]:
        replacements = {
            "{prompt_file}": str(prompt_path),
            "{repo_path}": str(request.repo_path),
            "{task}": request.task,
            "{stage}": request.stage,
        }

        if isinstance(self.command, str):
            formatted = self.command
            for placeholder, value in replacements.items():
                formatted = formatted.replace(placeholder, value)
            return shlex.split(formatted)

        command: list[str] = []
        for token in self.command:
            formatted = token
            for placeholder, value in replacements.items():
                formatted = formatted.replace(placeholder, value)
            command.append(formatted)
        return command


def load_agent_backends(config_path: Path) -> tuple[CommandTemplateAgent, CommandTemplateAgent]:
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    missing = [name for name in ("codex", "claude") if name not in payload]
    if missing:
        names = ", ".join(missing)
        raise ValueError(f"Missing agent config entries: {names}")

    codex_cfg = payload["codex"]
    claude_cfg = payload["claude"]
    return (
        CommandTemplateAgent(
            "codex",
            codex_cfg["command"],
            timeout_seconds=int(codex_cfg.get("timeout_seconds", 180)),
        ),
        CommandTemplateAgent(
            "claude",
            claude_cfg["command"],
            timeout_seconds=int(claude_cfg.get("timeout_seconds", 180)),
        ),
    )


def _parse_agent_output(raw_output: str) -> dict[str, Any]:
    cleaned = _strip_code_fences(raw_output)
    try:
        payload = json.loads(cleaned)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        pass
    return {
        "summary": "Fallback parser used because structured JSON was not returned.",
        "details": raw_output or "Agent returned no output.",
        "file_suggestions": [],
        "quality_score": 5,
        "risk_score": 5,
        "needs_follow_up": True,
    }


def _strip_code_fences(value: str) -> str:
    stripped = value.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        lines = stripped.splitlines()
        return "\n".join(lines[1:-1]).strip()
    return stripped


def _normalize_score(value: Any, *, default: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(0, min(10, number))


def _ensure_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        if isinstance(item, str) and item:
            result.append(item)
    return result


def _estimate_risk(task: str) -> int:
    keywords = {"auth", "payment", "billing", "security", "migration", "database"}
    lowered = task.lower()
    return 9 if any(keyword in lowered for keyword in keywords) else 5


def _infer_files(context: str) -> list[str]:
    files: list[str] = []
    for line in context.splitlines():
        stripped = line.strip().strip("`").strip("-").strip()
        if not stripped:
            continue
        if "/" in stripped or "." in stripped:
            if any(
                stripped.endswith(suffix)
                for suffix in (".py", ".md", ".json", ".toml", ".ts", ".tsx", ".js")
            ):
                if stripped not in files:
                    files.append(stripped)
    return files[:5] or ["README.md", "src/", "tests/"]
