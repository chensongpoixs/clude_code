from __future__ import annotations

from pathlib import Path

from ..types import ToolResult
from ..workspace import resolve_in_workspace


def write_file(*, workspace_root: Path, path: str, text: str) -> ToolResult:
    p = resolve_in_workspace(workspace_root, path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return ToolResult(True, payload={"path": path, "bytes_written": len(text.encode("utf-8"))})


