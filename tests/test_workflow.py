from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from patchpilot.agents import MockAgent
from patchpilot.cli import bundled_demo_repo
from patchpilot.workflow import AgentOrchestrator


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


if __name__ == "__main__":
    unittest.main()
