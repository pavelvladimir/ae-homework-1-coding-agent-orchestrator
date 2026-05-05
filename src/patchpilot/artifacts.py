from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from patchpilot.models import AgentResponse


class ArtifactWriter:
    def __init__(self, root: Path, task: str) -> None:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        slug = _slugify(task)
        self.output_dir = root.resolve() / f"{timestamp}_{slug}"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.manifest: list[str] = []

    def write_text(self, filename: str, content: str) -> Path:
        path = self.output_dir / filename
        path.write_text(content.rstrip() + "\n", encoding="utf-8")
        self.manifest.append(filename)
        return path

    def write_json(self, filename: str, payload: dict[str, Any]) -> Path:
        path = self.output_dir / filename
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        self.manifest.append(filename)
        return path

    def write_agent_response(self, stem: str, response: AgentResponse) -> None:
        self.write_text(f"{stem}.md", response.as_markdown())
        self.write_json(f"{stem}.json", response.to_dict())


def _slugify(value: str) -> str:
    raw = value.lower().strip()
    filtered = [char if char.isalnum() else "-" for char in raw]
    slug = "".join(filtered)
    while "--" in slug:
        slug = slug.replace("--", "-")
    slug = slug.strip("-")
    return slug[:48] or "run"
