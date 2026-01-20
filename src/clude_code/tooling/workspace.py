from __future__ import annotations

from pathlib import Path

from .types import ToolError

"""
将用户传入的相对路径解析到 workspace 内部（防止越权读写）。

规则：
- 以 workspace_root 为根拼接 user_path，再 resolve
- 若解析后的路径不在 workspace_root 下，抛 ToolError
"""
def resolve_in_workspace(workspace_root: Path, user_path: str) -> Path:

    root = workspace_root.resolve()
    p = (root / user_path).resolve()
    try:
        p.relative_to(root)
    except ValueError as e:
        raise ToolError(f"path is outside workspace: {user_path}") from e
    return p


