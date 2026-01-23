from __future__ import annotations

from pathlib import Path
from typing import Any

from ..types import ToolResult
from ..workspace import resolve_in_workspace
from ..logger_helper import get_tool_logger
from ...config.tools_config import get_directory_config

# 工具模块 logger（延迟初始化）
_logger = get_tool_logger(__name__)

# 默认最大项目数（避免大目录刷屏）
_DEFAULT_MAX_ITEMS = 100


def list_dir(
    *,
    workspace_root: Path,
    path: str = ".",
    max_items: int | None = None,
    include_size: bool = False,
) -> ToolResult:
    """
    列出目录内容（精简输出版本）。
    
    优化特性（Phase 4）：
    - 精简输出：默认不返回 size_bytes（可选开启）
    - 分页限制：max_items 防止大目录刷屏
    - 智能排序：目录在前，按名称字母排序
    
    Args:
        workspace_root: 工作区根目录
        path: 目标目录路径（相对工作区）
        max_items: 最大返回项数（默认 100）
        include_size: 是否包含文件大小（默认 False，节省 Token）
    """
    # 检查工具是否启用
    config = get_directory_config()
    if not config.enabled:
        _logger.warning("[ListDir] 目录列表工具已被禁用")
        return ToolResult(False, error={"code": "E_TOOL_DISABLED", "message": "directory tool is disabled"})

    _logger.debug(f"[ListDir] 开始列出目录: {path}, max_items={max_items}, include_size={include_size}")
    p = resolve_in_workspace(workspace_root, path)
    if not p.exists() or not p.is_dir():
        _logger.warning(f"[ListDir] 路径不存在或不是目录: {path}")
        return ToolResult(False, error={"code": "E_NOT_DIR", "message": f"not a directory: {path}"})
    
    # 使用配置或默认值
    eff_max_items = max_items if max_items is not None else _DEFAULT_MAX_ITEMS
    
    items: list[dict[str, Any]] = []
    truncated = False
    total_count = 0
    
    # 排序：目录在前，然后按名称字母排序
    try:
        children = sorted(
            p.iterdir(),
            key=lambda x: (not x.is_dir(), x.name.lower())  # 目录在前
        )
    except PermissionError:
        _logger.warning(f"[ListDir] 权限不足: {path}")
        return ToolResult(False, error={"code": "E_PERMISSION", "message": f"permission denied: {path}"})
    
    for child in children:
        total_count += 1
        
        if len(items) >= eff_max_items:
            truncated = True
            continue  # 继续计数但不添加
        
        # 构建条目（精简版本）
        entry: dict[str, Any] = {
            "name": child.name,
            "is_dir": child.is_dir(),
        }
        
        # 可选：包含文件大小
        if include_size and child.is_file():
            try:
                entry["size"] = child.stat().st_size
            except OSError:
                pass  # 忽略无法获取大小的文件
        
        items.append(entry)
    
    _logger.info(f"[ListDir] 列出目录成功: {path}, 返回: {len(items)}/{total_count} 项")
    
    # 构建响应
    payload: dict[str, Any] = {
        "path": path,
        "items": items,
    }
    
    if truncated:
        payload["truncated"] = True
        payload["total_count"] = total_count
        payload["returned_count"] = len(items)
    
    return ToolResult(True, payload=payload)


