from __future__ import annotations

from pathlib import Path


IGNORED_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    "node_modules",
    "runs",
}

TEXT_FILE_SUFFIXES = {
    ".py",
    ".md",
    ".txt",
    ".json",
    ".toml",
    ".yaml",
    ".yml",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".css",
    ".html",
}


def build_repo_snapshot(
    repo_path: Path,
    *,
    max_files: int = 30,
    max_excerpt_chars: int = 800,
    max_excerpts: int = 6,
) -> str:
    repo_path = repo_path.resolve()
    files = _list_files(repo_path, max_files=max_files)
    tree_lines = "\n".join(f"- `{path}`" for path in files) or "- Repository appears empty"

    excerpt_blocks: list[str] = []
    for relative_path in _pick_excerpt_files(files, limit=max_excerpts):
        excerpt = _read_excerpt(repo_path / relative_path, max_excerpt_chars=max_excerpt_chars)
        if excerpt:
            excerpt_blocks.append(
                f"### `{relative_path}`\n```text\n{excerpt}\n```"
            )

    excerpts = "\n\n".join(excerpt_blocks) or "No text excerpts collected."

    return (
        f"# Repository snapshot for `{repo_path}`\n\n"
        "## File tree\n"
        f"{tree_lines}\n\n"
        "## Key excerpts\n"
        f"{excerpts}\n"
    )


def _list_files(repo_path: Path, *, max_files: int) -> list[str]:
    collected: list[str] = []
    for path in sorted(repo_path.rglob("*")):
        if len(collected) >= max_files:
            break
        if not path.is_file():
            continue
        if any(part in IGNORED_DIRS for part in path.parts):
            continue
        if path.suffix and path.suffix.lower() not in TEXT_FILE_SUFFIXES:
            continue
        collected.append(path.relative_to(repo_path).as_posix())
    return collected


def _pick_excerpt_files(files: list[str], *, limit: int) -> list[str]:
    priority_prefixes = (
        "README",
        "pyproject.toml",
        "package.json",
        "src/",
        "tests/",
    )
    chosen: list[str] = []
    for prefix in priority_prefixes:
        for file_path in files:
            if len(chosen) >= limit:
                return chosen
            if file_path in chosen:
                continue
            if file_path.startswith(prefix):
                chosen.append(file_path)
    for file_path in files:
        if len(chosen) >= limit:
            break
        if file_path not in chosen:
            chosen.append(file_path)
    return chosen


def _read_excerpt(path: Path, *, max_excerpt_chars: int) -> str:
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""
    return content[:max_excerpt_chars].strip()
