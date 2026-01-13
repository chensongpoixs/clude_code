from __future__ import annotations

from pathlib import Path

from ..types import ToolResult
from ..workspace import resolve_in_workspace


_NOISE_DIRS = {".git", ".clude", "node_modules", ".venv", "dist", "build"}


def glob_file_search(*, workspace_root: Path, glob_pattern: str, target_directory: str = ".") -> ToolResult:
    """
    按名称模式查找文件（支持 `**/*.py` 递归）。
    """
    root = resolve_in_workspace(workspace_root, target_directory)
    if not root.exists() or not root.is_dir():
        return ToolResult(False, error={"code": "E_NOT_DIR", "message": f"not a directory: {target_directory}"})

    matches: list[str] = []
    try:
        for p in root.glob(glob_pattern):
            if not p.is_file():
                continue
            if any(part in p.parts for part in _NOISE_DIRS):
                continue
            rel = str(p.resolve().relative_to(workspace_root.resolve()))
            matches.append(rel)
    except Exception as e:
        return ToolResult(False, error={"code": "E_GLOB", "message": str(e)})

    return ToolResult(True, payload={"pattern": glob_pattern, "matches": sorted(matches)})


