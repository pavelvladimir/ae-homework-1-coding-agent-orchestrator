# PatchPilot

PatchPilot is a practical CLI project that orchestrates coding agents over a real repository task.
It takes one engineering task, sends it through a multi-agent workflow, and produces a reusable execution packet:

- parallel discovery notes
- a supervisor plan
- an implementation brief
- review / repair loop outputs
- a final go-no-go summary

The intended practical use is simple: when a team gets a GitHub issue, migration task, or bugfix request, PatchPilot turns the request into a structured packet that a developer can implement faster and with lower risk.

## Why this matches the homework

This repository demonstrates both workflow orchestration and multi-agent collaboration:

- Sequential: intake -> supervisor plan -> implementation brief -> final summary
- Parallel: Codex and Claude Code inspect the same task independently at the start
- Loop: implementation and review iterate until the approval threshold is reached
- Conditional: high-risk tasks switch into a risk-mitigation branch before normal implementation
- Collaboration: both agents receive each other's outputs in later stages
- Supervisor: a local supervisor combines both views and chooses the next branch

The project is practical because it creates artifacts that can be used immediately during real development work.

## Architecture

```text
Task + Repo Snapshot
        |
        v
 Parallel discovery
  - Codex: planner / implementer
  - Claude Code: reviewer / risk scout
        |
        v
 Local supervisor
  - merges outputs
  - picks branch
  - defines acceptance criteria
        |
        v
 Implementation brief
        |
        v
 Review / repair loop
  - Claude reviews
  - Codex revises if needed
        |
        v
 Final summary + saved artifacts
```

## Project structure

```text
.vscode/
src/patchpilot/
  agents.py
  artifacts.py
  cli.py
  models.py
  prompts.py
  repo_context.py
  workflow.py
examples/
  agents.example.json
  sample_service/
tests/
  test_workflow.py
```

Root workspace helpers are included as well:

- `.python-version` pins Python 3.13 for the root `uv` workflow
- `.nvmrc` pins Node.js 22 for the TypeScript sample app
- `.vscode/` contains ready-to-use tasks, launch configs, and editor settings

## Quick start

### Root Python workflow

The orchestrator is intended to be run with `uv`:

```bash
uv run patchpilot demo
```

This repository includes a local `uv.toml`, so `uv` keeps its cache inside the project instead of relying on a global cache path.

### 1. Run the built-in demo

```bash
uv run patchpilot demo
```

This uses deterministic mock agents and the bundled `examples/sample_service` repository, so it works even without API keys or installed agent CLIs.

### Bundled example repository

The demo target is a tiny `pnpm` + Fastify + TypeScript customer-support API service with a few realistic files:

- typed Fastify route modules for tickets and webhooks
- simple config and repository modules
- `tsconfig.json`, ESLint config, and `pnpm` scripts for lint/build/dev/test
- lightweight Vitest tests written in TypeScript
- a `TASKS.md` file with suggested orchestration scenarios

If you want to inspect or run the example app itself:

```bash
cd examples/sample_service
pnpm install
pnpm lint
pnpm build
pnpm test
pnpm dev
```

Or from the repository root:

```bash
pnpm --dir examples/sample_service install
pnpm --dir examples/sample_service lint
pnpm --dir examples/sample_service build
pnpm --dir examples/sample_service test
pnpm --dir examples/sample_service dev
```

Try these:

```bash
uv run patchpilot demo
uv run patchpilot demo --task "Prepare an implementation packet for adding idempotency to retrying Fastify webhook handlers"
uv run patchpilot demo --task "Plan a safe database migration from SQLite to Postgres for the support service"
```

### 2. Run on your own repository

```bash
uv run patchpilot run \
  --task "Add structured logging to API handlers" \
  --repo /path/to/repository \
  --mock
```

Artifacts are saved into `runs/<timestamp>_<task-slug>/`.

## Using real Codex and Claude Code

PatchPilot supports command-template agent backends. The config file maps each agent to the command you use locally.

Example file: `examples/agents.example.json`

```json
{
  "codex": {
    "command": ["codex", "exec", "--input-file", "{prompt_file}"],
    "timeout_seconds": 240
  },
  "claude": {
    "command": ["claude", "--print", "--prompt-file", "{prompt_file}"],
    "timeout_seconds": 240
  }
}
```

The exact command flags may differ on your machine. PatchPilot keeps that layer configurable on purpose.

Run with real backends:

```bash
uv run patchpilot run \
  --task "Migrate the project from SQLite to Postgres" \
  --repo /path/to/repository \
  --config examples/agents.example.json
```

## Example output

Each run creates artifacts like:

- `00_intake.md`
- `01_codex_parallel_discovery.md`
- `02_claude_parallel_review.md`
- `03_supervisor_plan.md`
- `04_implementation_brief.md` or `04_risk_mitigation_brief.md`
- `05_review_round_1.md`
- `06_repair_round_1.md`
- `99_final_summary.md`
- `manifest.json`

That makes the orchestration visible and easy to demo during a presentation.

## Verification

Run tests:

```bash
uv run python -m unittest discover -s tests
```

## Elevator pitch

PatchPilot is a practical orchestration layer for coding agents. Instead of asking one agent for one answer, it coordinates independent analysis, supervision, conditional branching, and iterative review to produce a safer implementation packet for real repository tasks.
