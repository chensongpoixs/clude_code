"""
工具结果缓存模块（方案 D）

避免重复调用相同工具，节省 token 和时间。

业界对标：
- Cursor: 基于文件修改时间的缓存
- Claude Code: 会话内结果缓存
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ============================================================
# 缓存条目
# ============================================================

@dataclass
class CacheEntry:
    """缓存条目"""
    value: Any
    created_at: float
    ttl: int  # 秒
    hit_count: int = 0
    
    def is_expired(self) -> bool:
        """检查是否过期"""
        return time.time() > self.created_at + self.ttl


# ============================================================
# 缓存配置
# ============================================================

@dataclass
class CacheConfig:
    """缓存配置"""
    # 各工具的 TTL（秒）
    ttl_grep: int = 60
    ttl_read_file: int = 120
    ttl_list_dir: int = 60
    ttl_glob_file_search: int = 120
    ttl_search_semantic: int = 300
    
    # 缓存限制
    max_entries: int = 100
    max_entry_size: int = 100_000  # 字节
    
    # 启用/禁用
    enabled: bool = True


DEFAULT_CONFIG = CacheConfig()


# ============================================================
# 工具缓存
# ============================================================

class ToolCache:
    """工具结果缓存"""
    
    def __init__(self, config: CacheConfig | None = None, workspace_root: Path | None = None):
        self.config = config or DEFAULT_CONFIG
        self.workspace_root = workspace_root or Path(".")
        self._cache: dict[str, CacheEntry] = {}
        self._stats = {
            "hits": 0,
            "misses": 0,
            "evictions": 0,
        }
    
    def get(self, key: str) -> tuple[bool, Any]:
        """
        获取缓存值。
        
        Returns:
            (hit, value): hit=True 表示命中，value 是缓存值
        """
        if not self.config.enabled:
            return False, None
        
        entry = self._cache.get(key)
        if entry is None:
            self._stats["misses"] += 1
            return False, None
        
        if entry.is_expired():
            del self._cache[key]
            self._stats["misses"] += 1
            return False, None
        
        entry.hit_count += 1
        self._stats["hits"] += 1
        return True, entry.value
    
    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """设置缓存值"""
        if not self.config.enabled:
            return
        
        # 检查大小限制
        try:
            size = len(json.dumps(value, ensure_ascii=False))
            if size > self.config.max_entry_size:
                return  # 太大，不缓存
        except (TypeError, ValueError):
            return  # 无法序列化，不缓存
        
        # 检查条目数限制
        if len(self._cache) >= self.config.max_entries:
            self._evict_oldest()
        
        self._cache[key] = CacheEntry(
            value=value,
            created_at=time.time(),
            ttl=ttl or 60,
        )
    
    def make_key(self, tool: str, args: dict[str, Any]) -> str:
        """
        生成缓存键。
        
        对于文件相关工具，会考虑文件修改时间。
        """
        base_key = f"{tool}:{json.dumps(args, sort_keys=True, ensure_ascii=False)}"
        
        # 文件相关工具：加入文件修改时间
        if tool in ("read_file", "list_dir", "glob_file_search"):
            path = args.get("path") or args.get("target_directory") or "."
            mtime = self._get_mtime(path)
            if mtime:
                base_key += f":mtime={mtime}"
        
        # 生成哈希
        return hashlib.md5(base_key.encode()).hexdigest()[:16]
    
    def get_ttl(self, tool: str) -> int:
        """获取工具的 TTL"""
        ttl_map = {
            "grep": self.config.ttl_grep,
            "read_file": self.config.ttl_read_file,
            "list_dir": self.config.ttl_list_dir,
            "glob_file_search": self.config.ttl_glob_file_search,
            "search_semantic": self.config.ttl_search_semantic,
        }
        return ttl_map.get(tool, 60)
    
    def invalidate(self, pattern: str | None = None) -> int:
        """
        使缓存失效。
        
        Args:
            pattern: 如果指定，只使匹配的键失效；否则清空所有
        
        Returns:
            失效的条目数
        """
        if pattern is None:
            count = len(self._cache)
            self._cache.clear()
            return count
        
        keys_to_remove = [k for k in self._cache if pattern in k]
        for k in keys_to_remove:
            del self._cache[k]
        return len(keys_to_remove)
    
    def get_stats(self) -> dict[str, Any]:
        """获取缓存统计"""
        total = self._stats["hits"] + self._stats["misses"]
        hit_rate = (self._stats["hits"] / total * 100) if total > 0 else 0
        return {
            **self._stats,
            "entries": len(self._cache),
            "hit_rate": f"{hit_rate:.1f}%",
        }
    
    def _get_mtime(self, path: str) -> float | None:
        """获取文件/目录修改时间"""
        try:
            full_path = self.workspace_root / path
            if full_path.exists():
                return full_path.stat().st_mtime
        except Exception:
            pass
        return None
    
    def _evict_oldest(self) -> None:
        """驱逐最旧的条目"""
        if not self._cache:
            return
        
        oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k].created_at)
        del self._cache[oldest_key]
        self._stats["evictions"] += 1


# ============================================================
# 单例实例
# ============================================================

_cache: ToolCache | None = None


def get_tool_cache(config: CacheConfig | None = None, workspace_root: Path | None = None) -> ToolCache:
    """获取工具缓存实例"""
    global _cache
    if _cache is None or config is not None:
        _cache = ToolCache(config, workspace_root)
    return _cache


def cache_tool_result(tool: str, args: dict[str, Any], result: Any) -> None:
    """便捷函数：缓存工具结果"""
    cache = get_tool_cache()
    key = cache.make_key(tool, args)
    ttl = cache.get_ttl(tool)
    cache.set(key, result, ttl)


def get_cached_result(tool: str, args: dict[str, Any]) -> tuple[bool, Any]:
    """便捷函数：获取缓存的工具结果"""
    cache = get_tool_cache()
    key = cache.make_key(tool, args)
    return cache.get(key)

