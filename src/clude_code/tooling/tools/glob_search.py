from __future__ import annotations

from pathlib import Path

from ..types import ToolResult
from ..workspace import resolve_in_workspace
from ..logger_helper import get_tool_logger
from ...config.tools_config import get_directory_config

# 工具模块 logger（延迟初始化）
_logger = get_tool_logger(__name__)


def glob_file_search(*, workspace_root: Path, glob_pattern: str, target_directory: str = ".") -> ToolResult:
    """
    按名称模式查找文件（支持 `**/*.py` 递归）。
    """
    # 检查工具是否启用
    config = get_directory_config()
    if not config.enabled:
        _logger.warning("[GlobSearch] 全局搜索工具已被禁用")
        return ToolResult(False, error={"code": "E_TOOL_DISABLED", "message": "directory tool is disabled"})

    _logger.debug(f"[GlobSearch] 开始搜索: pattern={glob_pattern}, directory={target_directory}")
    root = resolve_in_workspace(workspace_root, target_directory)
    if not root.exists() or not root.is_dir():
        _logger.warning(f"[GlobSearch] 目录不存在或不是目录: {target_directory}")
        return ToolResult(False, error={"code": "E_NOT_DIR", "message": f"not a directory: {target_directory}"})

    matches: list[str] = []
    try:
        ignore_dirs = set([str(x) for x in (getattr(config, "ignore_dirs", []) or [])])
        for p in root.glob(glob_pattern):
            if not p.is_file():
                continue
            if ignore_dirs and any(part in p.parts for part in ignore_dirs):
                continue
            rel = str(p.resolve().relative_to(workspace_root.resolve()))
            matches.append(rel)
        _logger.info(f"[GlobSearch] 搜索完成: pattern={glob_pattern}, 找到 {len(matches)} 个文件")
    except Exception as e:
        _logger.error(f"[GlobSearch] 搜索失败: {e}", exc_info=True)
        return ToolResult(False, error={"code": "E_GLOB", "message": str(e)})

    return ToolResult(True, payload={"pattern": glob_pattern, "matches": sorted(matches)})


