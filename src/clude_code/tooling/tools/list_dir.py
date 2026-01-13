from __future__ import annotations

from pathlib import Path

from ..types import ToolResult
from ..workspace import resolve_in_workspace


def list_dir(*, workspace_root: Path, path: str = ".") -> ToolResult:
    p = resolve_in_workspace(workspace_root, path)
    if not p.exists() or not p.is_dir():
        return ToolResult(False, error={"code": "E_NOT_DIR", "message": f"not a directory: {path}"})
    items: list[dict] = []
    for child in sorted(p.iterdir(), key=lambda x: x.name.lower()):
        items.append(
            {
                "name": child.name,
                "is_dir": child.is_dir(),
                "size_bytes": child.stat().st_size if child.is_file() else None,
            }
        )
    return ToolResult(True, payload={"path": path, "items": items})


