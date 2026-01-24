from __future__ import annotations

import heapq
import fnmatch
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

# 大目录阈值：超过此数量，使用堆排序优化
_LARGE_DIR_THRESHOLD = 1000


def list_dir(
    *,
    workspace_root: Path,
    path: str = ".",
    max_items: int | None = None,
    include_size: bool = False,
    show_hidden: bool = False,
    file_pattern: str | None = None,
) -> ToolResult:
    """
    列出目录内容（精简输出版本，业界最佳实践优化）。
    
    优化特性（Phase 4+）：
    - 精简输出：默认不返回 size_bytes（可选开启）
    - 分页限制：max_items 防止大目录刷屏
    - 智能排序：目录在前，按名称字母排序
    - 隐藏文件过滤：默认过滤以 `.` 开头的文件（节省 Token）
    - 文件类型过滤：支持 glob 模式（如 `*.py`）
    - 大目录优化：使用堆排序，只保留前 N 项
    
    Args:
        workspace_root: 工作区根目录
        path: 目标目录路径（相对工作区）
        max_items: 最大返回项数（默认 100）
        include_size: 是否包含文件大小（默认 False，节省 Token）
        show_hidden: 是否显示隐藏文件（默认 False，节省 Token）
        file_pattern: 文件类型过滤模式（如 `*.py`, `*.cpp`），None 表示不过滤
    """
    # 检查工具是否启用
    config = get_directory_config()
    if not config.enabled:
        _logger.warning("[ListDir] 目录列表工具已被禁用")
        return ToolResult(False, error={"code": "E_TOOL_DISABLED", "message": "directory tool is disabled"})

    _logger.debug(f"[ListDir] 开始列出目录: {path}, max_items={max_items}, include_size={include_size}, show_hidden={show_hidden}, file_pattern={file_pattern}")
    p = resolve_in_workspace(workspace_root, path)
    if not p.exists() or not p.is_dir():
        _logger.warning(f"[ListDir] 路径不存在或不是目录: {path}")
        return ToolResult(False, error={"code": "E_NOT_DIR", "message": f"not a directory: {path}"})
    
    # 使用配置或默认值
    eff_max_items = max_items if max_items is not None else _DEFAULT_MAX_ITEMS
    
    items: list[dict[str, Any]] = []
    truncated = False
    total_count = 0
    
    # 收集所有子项（用于估算大小）
    try:
        all_children = list(p.iterdir())
        total_count_estimate = len(all_children)
    except PermissionError:
        _logger.warning(f"[ListDir] 权限不足: {path}")
        return ToolResult(False, error={"code": "E_PERMISSION", "message": f"permission denied: {path}"})
    
    # 优化：大目录使用堆排序，小目录直接排序
    if total_count_estimate > _LARGE_DIR_THRESHOLD:
        _logger.debug(f"[ListDir] 大目录优化：使用堆排序（{total_count_estimate} 项 > {_LARGE_DIR_THRESHOLD}）")
        # 使用堆排序，只保留前 max_items 项
        items_heap: list[tuple[tuple[bool, str], Path]] = []
        for child in all_children:
            # 过滤隐藏文件
            if not show_hidden and child.name.startswith('.'):
                total_count += 1  # 计数但不添加
                continue
            
            # 过滤文件类型
            if file_pattern and not fnmatch.fnmatch(child.name, file_pattern):
                total_count += 1  # 计数但不添加
                continue
            
            total_count += 1
            key = (not child.is_dir(), child.name.lower())
            
            if len(items_heap) < eff_max_items:
                heapq.heappush(items_heap, (key, child))
            elif key < items_heap[0][0]:
                heapq.heapreplace(items_heap, (key, child))
        
        # 从堆中提取并排序
        sorted_items = sorted(items_heap, key=lambda x: x[0])
        children = [child for _, child in sorted_items]
        truncated = total_count > eff_max_items
    else:
        # 小目录：直接排序
        try:
            children = sorted(
                all_children,
                key=lambda x: (not x.is_dir(), x.name.lower())  # 目录在前
            )
        except PermissionError:
            _logger.warning(f"[ListDir] 权限不足: {path}")
            return ToolResult(False, error={"code": "E_PERMISSION", "message": f"permission denied: {path}"})
        
        # 统计总数（考虑过滤）
        for child in children:
            if not show_hidden and child.name.startswith('.'):
                continue
            if file_pattern and not fnmatch.fnmatch(child.name, file_pattern):
                continue
            total_count += 1
    
    # 构建条目列表
    for child in children:
        # 过滤隐藏文件
        if not show_hidden and child.name.startswith('.'):
            continue
        
        # 过滤文件类型
        if file_pattern and not fnmatch.fnmatch(child.name, file_pattern):
            continue
        
        if len(items) >= eff_max_items:
            truncated = True
            break  # 立即停止，不继续迭代
        
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


