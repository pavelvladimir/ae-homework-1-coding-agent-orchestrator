from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from patchpilot.agents import MockAgent, load_agent_backends
from patchpilot.workflow import AgentOrchestrator


DEFAULT_DEMO_TASK = "Prepare a safe implementation packet for adding request correlation logging to Fastify ticket routes"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="patchpilot",
        description="Practical orchestration of coding agents for repository tasks.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run the orchestrator on a custom task.")
    run_parser.add_argument("--task", required=True, help="Engineering task to orchestrate.")
    run_parser.add_argument("--repo", default=".", help="Path to the target repository.")
    run_parser.add_argument("--output-dir", default="runs", help="Directory for run artifacts.")
    run_parser.add_argument("--config", help="JSON file with real Codex / Claude command templates.")
    run_parser.add_argument("--mock", action="store_true", help="Use built-in mock agents.")
    run_parser.add_argument("--max-iterations", type=int, default=2, help="Max review loop rounds.")
    run_parser.add_argument(
        "--approval-threshold",
        type=int,
        default=8,
        help="Minimum review quality score required for approval.",
    )

    demo_parser = subparsers.add_parser("demo", help="Run a self-contained demo.")
    demo_parser.add_argument(
        "--repo",
        help="Path to the repository snapshot. Defaults to the bundled sample service.",
    )
    demo_parser.add_argument(
        "--task",
        default=DEFAULT_DEMO_TASK,
        help="Demo task to run against the bundled sample repository.",
    )
    demo_parser.add_argument("--output-dir", default="runs", help="Directory for run artifacts.")
    demo_parser.add_argument("--max-iterations", type=int, default=2, help="Max review loop rounds.")
    demo_parser.add_argument(
        "--approval-threshold",
        type=int,
        default=8,
        help="Minimum review quality score required for approval.",
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        asyncio.run(_run_cli(args))
    except (RuntimeError, ValueError) as exc:
        raise SystemExit(f"Error: {exc}") from exc


async def _run_cli(args: argparse.Namespace) -> None:
    if args.command == "demo":
        task = args.task
        codex_agent = MockAgent("codex")
        claude_agent = MockAgent("claude")
        repo_path = Path(args.repo) if args.repo else bundled_demo_repo()
    else:
        task = args.task
        repo_path = Path(args.repo)
        if args.mock or not args.config:
            codex_agent = MockAgent("codex")
            claude_agent = MockAgent("claude")
        else:
            config_path = _require_existing_file(
                Path(args.config),
                label="Agent config",
                hint="Use a real JSON path such as `examples/agents.example.json`.",
            )
            codex_agent, claude_agent = load_agent_backends(config_path)

    repo_path = _require_existing_directory(
        repo_path,
        label="Repository path",
        hint="Replace placeholder values like `/path/to/repository` with `.` or a real local path.",
    )

    orchestrator = AgentOrchestrator(
        codex_agent=codex_agent,
        claude_agent=claude_agent,
        output_root=Path(args.output_dir),
        max_iterations=args.max_iterations,
        approval_threshold=args.approval_threshold,
    )
    result = await orchestrator.run(task=task, repo_path=repo_path)

    print(f"Artifacts saved to: {result.output_dir}")
    print(f"Branch: {result.branch}")
    print(f"Approved: {'yes' if result.approved else 'no'}")
    print(f"Review rounds: {result.iterations}")
    print()
    if result.branch == "blocked":
        print("PatchPilot generated a diagnostic packet. It did not modify the target repository.")
    else:
        print("PatchPilot generated an orchestration packet. It did not modify the target repository.")
    print(f"Target repository: {result.repo_path}")
    print(f"Task: {result.task}")
    print(f"Implementation summary: {result.implementation_summary}")
    print(f"Reviewer signal: {result.final_review_summary}")
    print(f"Next step: {result.next_step}")
    if result.implementation_files:
        print("Suggested files:")
        for item in result.implementation_files:
            print(f"  - {item}")
    if result.backend_issues:
        print("Backend issues:")
        for item in result.backend_issues:
            print(f"  - {item}")
    print("Key artifacts:")
    for label, filename in result.key_artifacts.items():
        print(f"  - {label}: {result.output_dir / filename}")

    if result.backend_issues and args.command != "demo":
        raise SystemExit(2)


def bundled_demo_repo() -> Path:
    return Path(__file__).resolve().parents[2] / "examples" / "sample_service"


def _require_existing_directory(path: Path, *, label: str, hint: str) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.exists():
        raise ValueError(f"{label} does not exist: {path}. {hint}")
    if not resolved.is_dir():
        raise ValueError(f"{label} is not a directory: {path}. {hint}")
    return resolved


def _require_existing_file(path: Path, *, label: str, hint: str) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.exists():
        raise ValueError(f"{label} does not exist: {path}. {hint}")
    if not resolved.is_file():
        raise ValueError(f"{label} is not a file: {path}. {hint}")
    return resolved
