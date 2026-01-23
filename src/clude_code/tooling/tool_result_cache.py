"""
工具结果缓存模块（Phase 6）。

会话级 LRU 缓存，避免重复工具调用。
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """缓存条目"""
    result: dict[str, Any]
    timestamp: float = field(default_factory=time.time)
    hit_count: int = 0


class ToolResultCache:
    """
    工具结果缓存（会话级 LRU）。
    
    特性：
    - LRU 淘汰策略
    - 路径感知的失效机制
    - 可配置的最大容量
    
    用法：
        cache = ToolResultCache(max_size=100)
        
        # 获取缓存
        result = cache.get("read_file", {"path": "main.py"})
        
        # 设置缓存
        cache.set("read_file", {"path": "main.py"}, result_payload)
        
        # 写操作后失效
        cache.invalidate_path("main.py")
    """
    
    # 可缓存的只读工具
    CACHEABLE_TOOLS = frozenset({
        "read_file",
        "grep",
        "list_dir",
        "glob_file_search",
        "search_semantic",
        "websearch",  # 搜索结果可短期缓存
    })
    
    def __init__(self, max_size: int = 100, ttl_seconds: float = 300.0):
        """
        初始化缓存。
        
        Args:
            max_size: 最大缓存条目数
            ttl_seconds: 缓存过期时间（秒）
        """
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._max_size = max_size
        self._ttl = ttl_seconds
        self._stats = {
            "hits": 0,
            "misses": 0,
            "invalidations": 0,
        }
    
    def _make_key(self, tool: str, args: dict[str, Any]) -> str:
        """生成缓存键"""
        # 对参数进行排序和规范化
        normalized = json.dumps(args, sort_keys=True, ensure_ascii=False)
        key_str = f"{tool}:{normalized}"
        # 使用 MD5 作为短键
        return hashlib.md5(key_str.encode()).hexdigest()
    
    def _is_expired(self, entry: CacheEntry) -> bool:
        """检查条目是否过期"""
        return time.time() - entry.timestamp > self._ttl
    
    def is_cacheable(self, tool: str) -> bool:
        """检查工具是否可缓存"""
        return tool in self.CACHEABLE_TOOLS
    
    def get(self, tool: str, args: dict[str, Any]) -> dict[str, Any] | None:
        """
        获取缓存结果。
        
        Args:
            tool: 工具名称
            args: 工具参数
        
        Returns:
            缓存的结果，或 None（未命中/已过期）
        """
        if not self.is_cacheable(tool):
            return None
        
        key = self._make_key(tool, args)
        entry = self._cache.get(key)
        
        if entry is None:
            self._stats["misses"] += 1
            return None
        
        if self._is_expired(entry):
            del self._cache[key]
            self._stats["misses"] += 1
            return None
        
        # 命中：更新统计并移到末尾（LRU）
        entry.hit_count += 1
        self._stats["hits"] += 1
        self._cache.move_to_end(key)
        
        logger.debug(f"[ToolCache] 命中: {tool} (hits={entry.hit_count})")
        return entry.result
    
    def set(self, tool: str, args: dict[str, Any], result: dict[str, Any]) -> None:
        """
        设置缓存结果。
        
        Args:
            tool: 工具名称
            args: 工具参数
            result: 工具返回结果
        """
        if not self.is_cacheable(tool):
            return
        
        key = self._make_key(tool, args)
        
        # 检查容量
        while len(self._cache) >= self._max_size:
            # 淘汰最旧的条目（OrderedDict 头部）
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]
            logger.debug(f"[ToolCache] 淘汰: {oldest_key}")
        
        self._cache[key] = CacheEntry(result=result)
        logger.debug(f"[ToolCache] 缓存: {tool}")
    
    def invalidate_path(self, path: str) -> int:
        """
        失效与指定路径相关的缓存（细粒度失效）。
        
        失效策略：
        1. 精准匹配：缓存路径 == target 或以 target 结尾
        2. 父目录失效：如果 target 是 "src/main.py"，则 list_dir("src") 也失效
        
        Args:
            path: 被修改的文件路径
        
        Returns:
            失效的条目数
        """
        if not path:
            return 0
        
        # 规范化路径（统一分隔符）
        norm_path = path.replace("\\", "/").strip("/")
        
        # 提取父目录（用于失效 list_dir 缓存）
        parent_dir = "/".join(norm_path.split("/")[:-1]) if "/" in norm_path else ""
        
        keys_to_remove: list[str] = []
        
        for key, entry in self._cache.items():
            result = entry.result
            if not isinstance(result, dict):
                continue
            
            # 获取缓存条目的路径
            result_path = result.get("path") or result.get("file") or ""
            if not result_path:
                continue
            
            norm_result_path = str(result_path).replace("\\", "/").strip("/")
            
            # 策略 1: 精准匹配（文件读取、grep 等）
            if norm_result_path == norm_path or norm_result_path.endswith("/" + norm_path):
                keys_to_remove.append(key)
                continue
            
            # 策略 2: 父目录匹配（list_dir 缓存）
            # 如果缓存的是某个目录的列表，且被修改的文件在该目录下
            if parent_dir and norm_result_path == parent_dir:
                keys_to_remove.append(key)
                continue
            
            # 策略 3: 子路径匹配（glob_file_search 等可能缓存了包含该文件的结果）
            if "matches" in result and isinstance(result["matches"], list):
                # 检查 matches 列表中是否包含被修改的文件
                for match in result["matches"]:
                    if isinstance(match, str):
                        norm_match = match.replace("\\", "/").strip("/")
                        if norm_match == norm_path or norm_match.endswith("/" + norm_path):
                            keys_to_remove.append(key)
                            break
        
        # 去重（同一个 key 可能被多个策略命中）
        keys_to_remove = list(set(keys_to_remove))
        
        for key in keys_to_remove:
            del self._cache[key]
        
        if keys_to_remove:
            self._stats["invalidations"] += len(keys_to_remove)
            logger.debug(f"[ToolCache] 细粒度失效 {len(keys_to_remove)} 条目 (path={path})")
        
        return len(keys_to_remove)
    
    def clear(self) -> None:
        """清空所有缓存"""
        self._cache.clear()
        logger.debug("[ToolCache] 已清空")
    
    def get_stats(self) -> dict[str, Any]:
        """获取缓存统计"""
        total = self._stats["hits"] + self._stats["misses"]
        hit_rate = (self._stats["hits"] / total * 100) if total > 0 else 0.0
        
        return {
            "size": len(self._cache),
            "max_size": self._max_size,
            "hits": self._stats["hits"],
            "misses": self._stats["misses"],
            "hit_rate": f"{hit_rate:.1f}%",
            "invalidations": self._stats["invalidations"],
        }


# 全局缓存实例（会话级）
_session_cache: ToolResultCache | None = None


def get_session_cache() -> ToolResultCache:
    """获取会话级缓存实例"""
    global _session_cache
    if _session_cache is None:
        _session_cache = ToolResultCache()
    return _session_cache


def reset_session_cache() -> None:
    """重置会话缓存"""
    global _session_cache
    if _session_cache is not None:
        _session_cache.clear()
    _session_cache = None

