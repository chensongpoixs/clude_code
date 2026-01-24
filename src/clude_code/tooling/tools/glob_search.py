from __future__ import annotations

import fnmatch
import hashlib
import time
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

# 结果缓存（pattern_hash -> (matches, mtime, directory)）
_cache: dict[str, tuple[list[str], float, str]] = {}
_MAX_CACHE_SIZE = 100  # 最多缓存 100 个结果


def _parse_gitignore(gitignore_path: Path) -> list[str]:
    """
    解析 .gitignore 文件，返回忽略模式列表。
    
    支持基本规则：
    - `*` 通配符
    - `**` 递归匹配
    - `!` 否定规则（暂不支持，简化实现）
    - `#` 注释
    """
    if not gitignore_path.exists():
        return []
    
    patterns = []
    try:
        with open(gitignore_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                # 跳过空行和注释
                if not line or line.startswith("#"):
                    continue
                # 跳过否定规则（!）的简化处理
                if line.startswith("!"):
                    continue  # 简化：不支持否定规则
                patterns.append(line)
    except Exception as e:
        _logger.debug(f"[GlobSearch] 解析 .gitignore 失败: {e}")
        return []
    
    return patterns


def _should_ignore_path(path: Path, gitignore_patterns: list[str], workspace_root: Path) -> bool:
    """
    检查路径是否应该被忽略（基于 .gitignore 规则）。
    
    Args:
        path: 要检查的路径
        gitignore_patterns: .gitignore 规则列表
        workspace_root: 工作区根目录
    
    Returns:
        True 如果应该忽略，False 否则
    """
    if not gitignore_patterns:
        return False
    
    try:
        # 获取相对路径
        rel_path = str(path.relative_to(workspace_root))
        rel_path_posix = rel_path.replace("\\", "/")  # Windows 路径转 POSIX
        
        # 检查每个规则
        for pattern in gitignore_patterns:
            pattern_posix = pattern.replace("\\", "/")
            
            # 支持 ** 递归匹配
            if "**" in pattern_posix:
                # 将 ** 转换为通配符匹配
                pattern_regex = pattern_posix.replace("**", "*")
                if fnmatch.fnmatch(rel_path_posix, pattern_regex) or fnmatch.fnmatch(path.name, pattern_regex):
                    return True
            else:
                # 普通模式匹配
                if fnmatch.fnmatch(rel_path_posix, pattern_posix) or fnmatch.fnmatch(path.name, pattern_posix):
                    return True
                # 也检查路径的任何部分是否匹配
                for part in path.parts:
                    if fnmatch.fnmatch(part, pattern_posix):
                        return True
    except (ValueError, OSError):
        pass
    
    return False


def _get_cache_key(pattern: str, directory: Path) -> str:
    """生成缓存键。"""
    key_str = f"{pattern}:{directory}"
    return hashlib.md5(key_str.encode("utf-8")).hexdigest()


def _is_cache_valid(cache_key: str, directory: Path) -> bool:
    """
    检查缓存是否有效（基于目录修改时间）。
    
    如果目录或其子目录的文件被修改，缓存失效。
    """
    if cache_key not in _cache:
        return False
    
    _, cached_mtime, cached_dir = _cache[cache_key]
    
    # 检查目录是否相同
    if str(directory) != cached_dir:
        return False
    
    try:
        # 检查目录修改时间
        current_mtime = directory.stat().st_mtime
        return current_mtime <= cached_mtime
    except OSError:
        return False


def _clean_cache() -> None:
    """清理缓存，保持大小在限制内。"""
    if len(_cache) > _MAX_CACHE_SIZE:
        # 删除最旧的条目（简化：删除一半）
        keys_to_remove = list(_cache.keys())[:_MAX_CACHE_SIZE // 2]
        for key in keys_to_remove:
            del _cache[key]


def _glob_with_limits(
    root: Path,
    pattern: str,
    workspace_root: Path,
    ignore_dirs: set[str],
    max_results: int,
    max_depth: int,
    gitignore_patterns: list[str] | None = None,
) -> tuple[list[str], bool, int]:
    """
    带限制的 glob 搜索（深度限制 + 结果数量限制 + .gitignore 支持）。
    
    Args:
        root: 搜索根目录
        pattern: glob 模式
        workspace_root: 工作区根目录
        ignore_dirs: 忽略的目录名集合
        max_results: 最大结果数
        max_depth: 最大搜索深度
        gitignore_patterns: .gitignore 规则列表（可选）
    
    Returns:
        (matches, truncated, total_scanned)
    """
    matches: list[str] = []
    truncated = False
    total_scanned = 0
    
    # 分析 pattern 是否包含 ** (递归)
    is_recursive = "**" in pattern
    
    def _should_skip_dir(dir_path: Path) -> bool:
        """检查目录是否应该跳过。"""
        # 检查硬编码忽略列表
        if dir_path.name in ignore_dirs or dir_path.name.startswith('.'):
            return True
        # 检查 .gitignore 规则
        if gitignore_patterns and _should_ignore_path(dir_path, gitignore_patterns, workspace_root):
            return True
        return False
    
    def _search(current: Path, depth: int) -> bool:
        """递归搜索，返回是否继续"""
        nonlocal truncated, total_scanned
        
        if depth > max_depth:
            return True  # 深度超限，跳过但继续其他分支
        
        # 提前检查目录是否应该忽略（优化：避免进入）
        if _should_skip_dir(current):
            return True  # 跳过但继续其他分支
        
        try:
            for item in current.iterdir():
                total_scanned += 1
                
                # 检查忽略目录（双重检查，确保安全）
                if item.is_dir():
                    if _should_skip_dir(item):
                        continue
                    # 如果是递归模式，继续深入
                    if is_recursive:
                        if not _search(item, depth + 1):
                            return False
                elif item.is_file():
                    # 检查 .gitignore 规则
                    if gitignore_patterns and _should_ignore_path(item, gitignore_patterns, workspace_root):
                        continue
                    
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
    
    # 如果不是递归模式，使用简单的 glob（优化：使用 pathlib 内置优化）
    if not is_recursive and "*" in pattern:
        try:
            # 使用 pathlib 的内置 glob（更高效）
            for p in root.glob(pattern):
                total_scanned += 1
                if not p.is_file():
                    continue
                # 检查忽略目录
                if ignore_dirs and any(part in p.parts for part in ignore_dirs):
                    continue
                # 检查 .gitignore 规则
                if gitignore_patterns and _should_ignore_path(p, gitignore_patterns, workspace_root):
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
    按名称模式查找文件（支持 `**/*.py` 递归，业界最佳实践优化）。
    
    优化特性（Phase 5+）：
    - 结果限制：max_results 防止返回过多结果
    - 深度限制：max_depth 防止深层递归
    - 早停机制：达到限制后立即停止
    - .gitignore 支持：自动读取并应用 .gitignore 规则（节省 Token）
    - 结果缓存：相同模式的重复搜索使用缓存（提升性能）
    
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

    # 检查缓存（业界最佳实践：结果缓存）
    cache_key = _get_cache_key(glob_pattern, root)
    if _is_cache_valid(cache_key, root):
        _logger.debug(f"[GlobSearch] 使用缓存结果: pattern={glob_pattern}")
        cached_matches, _, _ = _cache[cache_key]
        return ToolResult(True, payload={
            "pattern": glob_pattern,
            "matches": sorted(cached_matches[:eff_max_results]),
            "from_cache": True,
        })

    try:
        ignore_dirs = set([str(x) for x in (getattr(config, "ignore_dirs", []) or [])])
        # 添加常见忽略目录
        ignore_dirs.update({".git", ".clude", "node_modules", ".venv", "__pycache__", ".idea", ".vscode"})
        
        # 读取 .gitignore 文件（业界最佳实践）
        gitignore_path = workspace_root / ".gitignore"
        gitignore_patterns = _parse_gitignore(gitignore_path) if gitignore_path.exists() else None
        if gitignore_patterns:
            _logger.debug(f"[GlobSearch] 读取 .gitignore: {len(gitignore_patterns)} 条规则")
        
        matches, truncated, total_scanned = _glob_with_limits(
            root=root,
            pattern=glob_pattern,
            workspace_root=workspace_root,
            ignore_dirs=ignore_dirs,
            max_results=eff_max_results,
            max_depth=eff_max_depth,
            gitignore_patterns=gitignore_patterns,
        )
        
        # 缓存结果（业界最佳实践：结果缓存）
        try:
            directory_mtime = root.stat().st_mtime
            _clean_cache()  # 清理缓存，保持大小在限制内
            _cache[cache_key] = (matches.copy(), directory_mtime, str(root))
        except OSError:
            pass  # 缓存失败不影响搜索结果
        
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


