from __future__ import annotations

from pathlib import Path

from ..types import ToolResult
from ..workspace import resolve_in_workspace
from ..logger_helper import get_tool_logger
from ...config.tools_config import get_directory_config

# 工具模块 logger（延迟初始化）
_logger = get_tool_logger(__name__)


def list_dir(*, workspace_root: Path, path: str = ".") -> ToolResult:
    # 检查工具是否启用
    config = get_directory_config()
    if not config.enabled:
        _logger.warning("[ListDir] 目录列表工具已被禁用")
        return ToolResult(False, error={"code": "E_TOOL_DISABLED", "message": "directory tool is disabled"})

    _logger.debug(f"[ListDir] 开始列出目录: {path}")
    p = resolve_in_workspace(workspace_root, path)
    if not p.exists() or not p.is_dir():
        _logger.warning(f"[ListDir] 路径不存在或不是目录: {path}")
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
    _logger.info(f"[ListDir] 列出目录成功: {path}, 项目数: {len(items)}")
    return ToolResult(True, payload={"path": path, "items": items})


