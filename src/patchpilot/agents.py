from __future__ import annotations

import abc
import asyncio
import json
import os
import re
import shutil
import shlex
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from patchpilot.models import AgentRequest, AgentResponse, AgentRole
from patchpilot.prompts import build_agent_prompt, build_agent_response_schema


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
            backend_issue=None,
            next_step_hint=None,
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
        schema = build_agent_response_schema()
        schema_json = json.dumps(schema, separators=(",", ":"))

        prompt_path = _write_temp_file(prompt, suffix=".txt")
        schema_path = _write_temp_file(json.dumps(schema, indent=2), suffix=".json")
        response_path = Path(tempfile.mkstemp(suffix=".json")[1])

        try:
            command = self._format_command(
                request=request,
                prompt=prompt,
                prompt_path=prompt_path,
                schema_path=schema_path,
                schema_json=schema_json,
                response_path=response_path,
            )
            try:
                completed = await asyncio.to_thread(
                    subprocess.run,
                    command,
                    cwd=str(request.repo_path),
                    input=prompt if _should_pipe_prompt(command) else None,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_seconds,
                    check=False,
                )
            except FileNotFoundError as exc:
                executable = command[0] if command else "<empty command>"
                raise RuntimeError(
                    f"Agent command not found for '{self.name}': {executable}. "
                    "Install the CLI or update the command in your agent config."
                ) from exc

            stdout = completed.stdout.strip()
            stderr = completed.stderr.strip()
            response_file_output = _read_optional_output(response_path)
            raw_output = response_file_output or stdout or stderr
            if completed.returncode != 0 and not raw_output:
                raw_output = f"Agent exited with code {completed.returncode}"

            parsed_payload = _coerce_agent_payload(raw_output)
            issue = _detect_backend_issue(self.name, raw_output, completed.returncode)
            payload = parsed_payload or _build_backend_issue_payload(issue, raw_output)
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
                backend_issue=issue["summary"] if issue else None,
                next_step_hint=issue["next_step_hint"] if issue else None,
                raw_output=raw_output,
                metadata={
                    "backend": "command",
                    "returncode": completed.returncode,
                    "stderr_present": bool(stderr),
                    "used_response_file": bool(response_file_output),
                    "backend_issue_code": issue["code"] if issue else "",
                },
            )
        finally:
            _unlink_if_exists(prompt_path)
            _unlink_if_exists(schema_path)
            _unlink_if_exists(response_path)

    def _format_command(
        self,
        *,
        request: AgentRequest,
        prompt: str,
        prompt_path: Path,
        schema_path: Path,
        schema_json: str,
        response_path: Path,
    ) -> list[str]:
        replacements = {
            "{prompt}": prompt,
            "{prompt_file}": str(prompt_path),
            "{schema_file}": str(schema_path),
            "{schema_json}": schema_json,
            "{response_file}": str(response_path),
            "{repo_path}": str(request.repo_path),
            "{task}": request.task,
            "{stage}": request.stage,
        }

        if isinstance(self.command, str):
            formatted = self.command
            for placeholder, value in replacements.items():
                formatted = formatted.replace(placeholder, value)
            return _resolve_executable(shlex.split(formatted))

        command: list[str] = []
        for token in self.command:
            formatted = token
            for placeholder, value in replacements.items():
                formatted = formatted.replace(placeholder, value)
            command.append(formatted)
        return _resolve_executable(command)


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


def _build_backend_issue_payload(
    issue: dict[str, str] | None,
    raw_output: str,
) -> dict[str, Any]:
    if issue:
        return {
            "summary": issue["summary"],
            "details": issue["details"],
            "file_suggestions": [],
            "quality_score": 0,
            "risk_score": 10,
            "needs_follow_up": True,
        }
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


def _coerce_agent_payload(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        if _has_expected_payload_keys(value):
            return value
        for key in ("result", "content", "message", "output", "response"):
            nested = value.get(key)
            payload = _coerce_agent_payload(nested)
            if payload:
                return payload
        return None

    if isinstance(value, list):
        for item in value:
            payload = _coerce_agent_payload(item)
            if payload:
                return payload
        return None

    if isinstance(value, str):
        candidates = [value, _strip_code_fences(value)]
        fenced_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", value, flags=re.DOTALL)
        if fenced_match:
            candidates.append(fenced_match.group(1))
        extracted = _extract_first_json_object(value)
        if extracted:
            candidates.append(extracted)

        for candidate in candidates:
            candidate = candidate.strip()
            if not candidate:
                continue
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            payload = _coerce_agent_payload(parsed)
            if payload:
                return payload
    return None


def _detect_backend_issue(
    agent_name: str,
    raw_output: str,
    returncode: int,
) -> dict[str, str] | None:
    if returncode == 0:
        return None

    lowered = raw_output.lower()
    excerpt = _summarize_raw_output(raw_output)

    if agent_name == "codex" and (
        "cannot access session files" in lowered
        or "attempt to write a readonly database" in lowered
        or (".codex/sessions" in raw_output and "permission denied" in lowered)
    ):
        return {
            "code": "codex-session-permissions",
            "summary": "Codex CLI could not start because session persistence under `~/.codex` is not writable from this environment.",
            "details": (
                "Codex never reached the planning step because it failed during session startup.\n\n"
                "Raw output excerpt:\n"
                f"{excerpt}"
            ),
            "next_step_hint": (
                "Keep `--ephemeral` in the Codex command template for non-interactive runs. "
                "If you are launching PatchPilot from inside the Codex app sandbox, rerun the "
                "real backend flow from your normal Terminal app. Otherwise fix ownership and "
                "permissions under `~/.codex`."
            ),
        }

    if agent_name == "claude" and "not logged in" in lowered:
        return {
            "code": "claude-auth-required",
            "summary": "Claude Code is installed, but it is not authenticated on this machine.",
            "details": (
                "Claude returned an authentication error before any review could run.\n\n"
                "Raw output excerpt:\n"
                f"{excerpt}"
            ),
            "next_step_hint": (
                "Run `claude auth status` to confirm the state, then sign in with `/login` "
                "or configure a token with `claude setup-token` before rerunning PatchPilot."
            ),
        }

    if agent_name == "codex" and (
        "failed to lookup address information" in lowered
        or "error sending request for url (https://api.openai.com/v1/responses)" in lowered
    ):
        return {
            "code": "codex-network-unavailable",
            "summary": "Codex CLI started, but it could not reach the OpenAI API from this environment.",
            "details": (
                "Codex got past local startup, then failed while contacting the remote model API.\n\n"
                "Raw output excerpt:\n"
                f"{excerpt}"
            ),
            "next_step_hint": (
                "Run the real backend flow from a normal Terminal session with outbound network "
                "access, or restore DNS / HTTPS access to `api.openai.com` before rerunning."
            ),
        }

    if "unexpected argument" in lowered or "unknown option" in lowered:
        return {
            "code": "command-template-mismatch",
            "summary": "The installed agent CLI rejected the configured command flags.",
            "details": (
                "PatchPilot reached the executable, but the local CLI syntax does not match the "
                "configured command template.\n\n"
                "Raw output excerpt:\n"
                f"{excerpt}"
            ),
            "next_step_hint": (
                "Update the command template in your agent config so it matches the CLI version "
                "installed on this machine."
            ),
        }

    return None


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


def _extract_first_json_object(value: str) -> str | None:
    start = value.find("{")
    while start != -1:
        depth = 0
        in_string = False
        escape = False
        for index in range(start, len(value)):
            char = value[index]
            if in_string:
                if escape:
                    escape = False
                elif char == "\\":
                    escape = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return value[start : index + 1]
        start = value.find("{", start + 1)
    return None


def _has_expected_payload_keys(value: dict[str, Any]) -> bool:
    required = {
        "summary",
        "details",
        "file_suggestions",
        "quality_score",
        "risk_score",
        "needs_follow_up",
    }
    return required.issubset(value.keys())


def _resolve_executable(command: list[str]) -> list[str]:
    if not command:
        return command

    executable = command[0]
    if "/" in executable:
        return command

    resolved = shutil.which(executable)
    if not resolved:
        return command

    return [resolved, *command[1:]]


def _should_pipe_prompt(command: list[str]) -> bool:
    return bool(command) and command[-1] == "-"


def _write_temp_file(content: str, *, suffix: str) -> Path:
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=suffix,
        delete=False,
    ) as handle:
        handle.write(content)
        return Path(handle.name)


def _read_optional_output(path: Path) -> str:
    try:
        content = path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    return content


def _unlink_if_exists(path: Path) -> None:
    try:
        os.unlink(path)
    except FileNotFoundError:
        return
    except OSError:
        return


def _estimate_risk(task: str) -> int:
    keywords = {"auth", "payment", "billing", "security", "migration", "database"}
    lowered = task.lower()
    return 9 if any(keyword in lowered for keyword in keywords) else 5


def _infer_files(context: str) -> list[str]:
    files: list[str] = []
    for candidate in re.findall(r"`([^`]+)`", context):
        cleaned = candidate.strip()
        if _looks_like_repo_file(cleaned) and cleaned not in files:
            files.append(cleaned)

    for line in context.splitlines():
        stripped = line.strip().lstrip("-# ").strip()
        if not stripped:
            continue
        if _looks_like_repo_file(stripped) and stripped not in files:
            files.append(stripped)
    return files[:5] or ["README.md", "src/", "tests/"]


def _looks_like_repo_file(value: str) -> bool:
    return any(
        value.endswith(suffix)
        for suffix in (".py", ".md", ".json", ".toml", ".ts", ".tsx", ".js", ".mjs")
    )


def _summarize_raw_output(raw_output: str, *, max_lines: int = 6) -> str:
    lines = [line.strip() for line in raw_output.splitlines() if line.strip()]
    if not lines:
        return "No output captured."

    if len(lines) <= max_lines:
        return "\n".join(lines)

    head = lines[: max_lines - 1]
    head.append("...")
    head.append(lines[-1])
    return "\n".join(head)
