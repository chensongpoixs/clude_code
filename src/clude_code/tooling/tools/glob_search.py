from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Any, Iterator

from ..types import ToolResult
from ..workspace import resolve_in_workspace
from ..logger_helper import get_tool_logger
from ...config.tools_config import get_directory_config

# 工具模块 logger（延迟初始化）
_logger = get_tool_logger(__name__)

# 默认限制
_DEFAULT_MAX_RESULTS = 200
_DEFAULT_MAX_DEPTH = 10


def _glob_with_limits(
    root: Path,
    pattern: str,
    workspace_root: Path,
    ignore_dirs: set[str],
    max_results: int,
    max_depth: int,
) -> tuple[list[str], bool, int]:
    """
    带限制的 glob 搜索（深度限制 + 结果数量限制）。
    
    Args:
        root: 搜索根目录
        pattern: glob 模式
        workspace_root: 工作区根目录
        ignore_dirs: 忽略的目录名集合
        max_results: 最大结果数
        max_depth: 最大搜索深度
    
    Returns:
        (matches, truncated, total_scanned)
    """
    matches: list[str] = []
    truncated = False
    total_scanned = 0
    
    # 分析 pattern 是否包含 ** (递归)
    is_recursive = "**" in pattern
    
    def _search(current: Path, depth: int) -> bool:
        """递归搜索，返回是否继续"""
        nonlocal truncated, total_scanned
        
        if depth > max_depth:
            return True  # 深度超限，跳过但继续其他分支
        
        try:
            for item in current.iterdir():
                total_scanned += 1
                
                # 检查忽略目录
                if item.is_dir():
                    if item.name in ignore_dirs or item.name.startswith('.'):
                        continue
                    # 如果是递归模式，继续深入
                    if is_recursive:
                        if not _search(item, depth + 1):
                            return False
                elif item.is_file():
                    # 匹配 pattern
                    try:
                        # 获取相对路径
                        rel_path = item.relative_to(root)
                        
                        # 使用 fnmatch 匹配
                        if fnmatch.fnmatch(str(rel_path), pattern) or fnmatch.fnmatch(item.name, pattern.split('/')[-1] if '/' in pattern else pattern):
                            full_rel = str(item.resolve().relative_to(workspace_root.resolve()))
                            matches.append(full_rel)
                            
                            if len(matches) >= max_results:
                                truncated = True
                                return False
                    except (ValueError, OSError):
                        pass
        except PermissionError:
            pass
        
        return True
    
    # 如果不是递归模式，使用简单的 glob
    if not is_recursive:
        try:
            for p in root.glob(pattern):
                total_scanned += 1
                if not p.is_file():
                    continue
                if ignore_dirs and any(part in p.parts for part in ignore_dirs):
                    continue
                rel = str(p.resolve().relative_to(workspace_root.resolve()))
                matches.append(rel)
                if len(matches) >= max_results:
                    truncated = True
                    break
        except Exception:
            pass
    else:
        # 递归模式，使用自定义搜索
        _search(root, 0)
    
    return matches, truncated, total_scanned


def glob_file_search(
    *,
    workspace_root: Path,
    glob_pattern: str,
    target_directory: str = ".",
    max_results: int | None = None,
    max_depth: int | None = None,
) -> ToolResult:
    """
    按名称模式查找文件（支持 `**/*.py` 递归）。
    
    优化特性（Phase 5）：
    - 结果限制：max_results 防止返回过多结果
    - 深度限制：max_depth 防止深层递归
    - 早停机制：达到限制后立即停止
    
    Args:
        workspace_root: 工作区根目录
        glob_pattern: glob 模式（如 **/*.py）
        target_directory: 搜索目录
        max_results: 最大结果数（默认 200）
        max_depth: 最大搜索深度（默认 10）
    """
    # 检查工具是否启用
    config = get_directory_config()
    if not config.enabled:
        _logger.warning("[GlobSearch] 全局搜索工具已被禁用")
        return ToolResult(False, error={"code": "E_TOOL_DISABLED", "message": "directory tool is disabled"})

    # 使用配置或默认值
    eff_max_results = max_results if max_results is not None else _DEFAULT_MAX_RESULTS
    eff_max_depth = max_depth if max_depth is not None else _DEFAULT_MAX_DEPTH

    _logger.debug(f"[GlobSearch] 开始搜索: pattern={glob_pattern}, directory={target_directory}, max_results={eff_max_results}, max_depth={eff_max_depth}")
    root = resolve_in_workspace(workspace_root, target_directory)
    if not root.exists() or not root.is_dir():
        _logger.warning(f"[GlobSearch] 目录不存在或不是目录: {target_directory}")
        return ToolResult(False, error={"code": "E_NOT_DIR", "message": f"not a directory: {target_directory}"})

    try:
        ignore_dirs = set([str(x) for x in (getattr(config, "ignore_dirs", []) or [])])
        # 添加常见忽略目录
        ignore_dirs.update({".git", ".clude", "node_modules", ".venv", "__pycache__", ".idea", ".vscode"})
        
        matches, truncated, total_scanned = _glob_with_limits(
            root=root,
            pattern=glob_pattern,
            workspace_root=workspace_root,
            ignore_dirs=ignore_dirs,
            max_results=eff_max_results,
            max_depth=eff_max_depth,
        )
        
        _logger.info(f"[GlobSearch] 搜索完成: pattern={glob_pattern}, 找到 {len(matches)} 个文件, 扫描 {total_scanned} 项, truncated={truncated}")
    except Exception as e:
        _logger.error(f"[GlobSearch] 搜索失败: {e}", exc_info=True)
        return ToolResult(False, error={"code": "E_GLOB", "message": str(e)})

    # 构建响应
    payload: dict[str, Any] = {
        "pattern": glob_pattern,
        "matches": sorted(matches),
    }
    
    if truncated:
        payload["truncated"] = True
        payload["returned_count"] = len(matches)
        payload["max_results"] = eff_max_results

    return ToolResult(True, payload=payload)


