"""
工具调用监控模块（方案 F）

记录工具调用统计，用于后续优化分析。

业界对标：
- OpenAI: 函数调用统计
- LangChain: 工具使用分析
"""

from __future__ import annotations

import json
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


# ============================================================
# 调用记录
# ============================================================

@dataclass
class ToolCallRecord:
    """单次工具调用记录"""
    tool: str
    timestamp: float
    duration_ms: float
    tokens_input: int
    tokens_output: int
    cached: bool
    success: bool
    error_code: str | None = None


# ============================================================
# 工具统计
# ============================================================

@dataclass
class ToolStats:
    """单个工具的统计数据"""
    call_count: int = 0
    success_count: int = 0
    cache_hits: int = 0
    total_duration_ms: float = 0
    total_tokens_input: int = 0
    total_tokens_output: int = 0
    error_counts: dict[str, int] = field(default_factory=dict)
    
    @property
    def success_rate(self) -> float:
        return (self.success_count / self.call_count * 100) if self.call_count > 0 else 0
    
    @property
    def cache_hit_rate(self) -> float:
        return (self.cache_hits / self.call_count * 100) if self.call_count > 0 else 0
    
    @property
    def avg_duration_ms(self) -> float:
        return (self.total_duration_ms / self.call_count) if self.call_count > 0 else 0
    
    @property
    def total_tokens(self) -> int:
        return self.total_tokens_input + self.total_tokens_output


# ============================================================
# 监控器
# ============================================================

class ToolMetrics:
    """工具调用监控器"""
    
    def __init__(self, session_id: str | None = None):
        self.session_id = session_id or f"session_{int(time.time())}"
        self.start_time = time.time()
        self._records: list[ToolCallRecord] = []
        self._stats: dict[str, ToolStats] = defaultdict(ToolStats)
    
    def record_call(
        self,
        tool: str,
        duration_ms: float,
        tokens_input: int = 0,
        tokens_output: int = 0,
        cached: bool = False,
        success: bool = True,
        error_code: str | None = None
    ) -> None:
        """记录工具调用"""
        record = ToolCallRecord(
            tool=tool,
            timestamp=time.time(),
            duration_ms=duration_ms,
            tokens_input=tokens_input,
            tokens_output=tokens_output,
            cached=cached,
            success=success,
            error_code=error_code
        )
        self._records.append(record)
        
        # 更新统计
        stats = self._stats[tool]
        stats.call_count += 1
        stats.total_duration_ms += duration_ms
        stats.total_tokens_input += tokens_input
        stats.total_tokens_output += tokens_output
        
        if cached:
            stats.cache_hits += 1
        if success:
            stats.success_count += 1
        if error_code:
            stats.error_counts[error_code] = stats.error_counts.get(error_code, 0) + 1
    
    def get_tool_stats(self, tool: str) -> ToolStats | None:
        """获取单个工具的统计"""
        return self._stats.get(tool)
    
    def get_summary(self) -> dict[str, Any]:
        """获取总体统计摘要"""
        total_calls = sum(s.call_count for s in self._stats.values())
        total_tokens = sum(s.total_tokens for s in self._stats.values())
        total_cache_hits = sum(s.cache_hits for s in self._stats.values())
        
        # 按调用频率排序
        top_tools = sorted(
            self._stats.items(),
            key=lambda x: x[1].call_count,
            reverse=True
        )[:5]
        
        return {
            "session_id": self.session_id,
            "duration_s": int(time.time() - self.start_time),
            "total_calls": total_calls,
            "total_tokens": total_tokens,
            "cache_hit_rate": f"{(total_cache_hits / total_calls * 100) if total_calls > 0 else 0:.1f}%",
            "top_tools": [
                {
                    "tool": name,
                    "calls": stats.call_count,
                    "tokens": stats.total_tokens,
                    "success_rate": f"{stats.success_rate:.1f}%",
                }
                for name, stats in top_tools
            ],
            "tools_used": len(self._stats),
        }
    
    def get_detailed_stats(self) -> dict[str, dict[str, Any]]:
        """获取详细统计"""
        return {
            tool: {
                "call_count": stats.call_count,
                "success_rate": f"{stats.success_rate:.1f}%",
                "cache_hit_rate": f"{stats.cache_hit_rate:.1f}%",
                "avg_duration_ms": f"{stats.avg_duration_ms:.1f}",
                "total_tokens_input": stats.total_tokens_input,
                "total_tokens_output": stats.total_tokens_output,
                "errors": stats.error_counts,
            }
            for tool, stats in sorted(self._stats.items())
        }
    
    def export_to_file(self, path: Path) -> None:
        """导出统计到文件"""
        data = {
            "session_id": self.session_id,
            "start_time": datetime.fromtimestamp(self.start_time).isoformat(),
            "summary": self.get_summary(),
            "detailed_stats": self.get_detailed_stats(),
            "records_count": len(self._records),
        }
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    
    def reset(self) -> None:
        """重置统计"""
        self._records.clear()
        self._stats.clear()


# ============================================================
# 单例实例
# ============================================================

_metrics: ToolMetrics | None = None


def get_tool_metrics(session_id: str | None = None) -> ToolMetrics:
    """获取监控器实例"""
    global _metrics
    if _metrics is None or session_id is not None:
        _metrics = ToolMetrics(session_id)
    return _metrics


def record_tool_call(
    tool: str,
    duration_ms: float,
    tokens_input: int = 0,
    tokens_output: int = 0,
    cached: bool = False,
    success: bool = True,
    error_code: str | None = None
) -> None:
    """便捷函数：记录工具调用"""
    get_tool_metrics().record_call(
        tool=tool,
        duration_ms=duration_ms,
        tokens_input=tokens_input,
        tokens_output=tokens_output,
        cached=cached,
        success=success,
        error_code=error_code
    )

