"""
成本追踪模块（Cost Tracker）

功能：
1. 记录每次 LLM 调用的 token 消耗
2. 根据厂商定价计算费用
3. 提供会话级和全局级统计

设计原则：
- 线程安全
- 支持持久化（可选）
- 与具体厂商解耦
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


# 厂商定价表（每 1K tokens，单位 USD）
# 数据来源：各厂商官方定价页面（2026-01）
PRICING_TABLE: dict[str, dict[str, dict[str, float]]] = {
    "openai": {
        "gpt-4o": {"input": 0.0025, "output": 0.01},
        "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
        "gpt-4-turbo": {"input": 0.01, "output": 0.03},
        "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015},
        "o1-preview": {"input": 0.015, "output": 0.06},
        "o1-mini": {"input": 0.003, "output": 0.012},
    },
    "anthropic": {
        "claude-3-5-sonnet-latest": {"input": 0.003, "output": 0.015},
        "claude-3-5-haiku-latest": {"input": 0.0008, "output": 0.004},
        "claude-3-opus-latest": {"input": 0.015, "output": 0.075},
    },
    "deepseek": {
        "deepseek-chat": {"input": 0.00014, "output": 0.00028},
        "deepseek-coder": {"input": 0.00014, "output": 0.00028},
        "deepseek-reasoner": {"input": 0.00055, "output": 0.00219},
    },
    "moonshot": {
        "moonshot-v1-8k": {"input": 0.000012, "output": 0.000012},
        "moonshot-v1-32k": {"input": 0.000024, "output": 0.000024},
        "moonshot-v1-128k": {"input": 0.00006, "output": 0.00006},
    },
    "zhipu": {
        "glm-4": {"input": 0.0001, "output": 0.0001},
        "glm-4-flash": {"input": 0.000001, "output": 0.000001},
        "glm-4-plus": {"input": 0.00005, "output": 0.00005},
    },
    "qianwen": {
        "qwen-turbo": {"input": 0.000002, "output": 0.000006},
        "qwen-plus": {"input": 0.000004, "output": 0.000012},
        "qwen-max": {"input": 0.00002, "output": 0.00006},
    },
    "groq": {
        "llama-3.3-70b-versatile": {"input": 0.00059, "output": 0.00079},
        "mixtral-8x7b-32768": {"input": 0.00024, "output": 0.00024},
    },
    # 免费或本地模型
    "ollama": {"*": {"input": 0.0, "output": 0.0}},
    "openai_compat": {"*": {"input": 0.0, "output": 0.0}},
}


@dataclass
class UsageRecord:
    """单次调用记录"""
    timestamp: datetime
    provider_id: str
    model_id: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    latency_ms: int
    success: bool = True
    error: str | None = None


@dataclass
class CostSummary:
    """成本汇总"""
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    total_latency_ms: int = 0
    avg_latency_ms: float = 0.0
    
    # 按厂商/模型统计
    by_provider: dict[str, dict[str, Any]] = field(default_factory=dict)
    by_model: dict[str, dict[str, Any]] = field(default_factory=dict)


class CostTracker:
    """
    成本追踪器
    
    用法：
        tracker = CostTracker()
        tracker.record_usage(
            provider_id="openai",
            model_id="gpt-4o",
            prompt_tokens=1000,
            completion_tokens=500,
            latency_ms=1200,
        )
        summary = tracker.get_summary()
    """
    
    def __init__(self, session_id: str | None = None):
        self.session_id = session_id or datetime.now().strftime("%Y%m%d_%H%M%S")
        self._records: list[UsageRecord] = []
        self._lock = threading.Lock()
    
    def _get_pricing(self, provider_id: str, model_id: str) -> dict[str, float]:
        """获取模型定价"""
        provider_pricing = PRICING_TABLE.get(provider_id, {})
        
        # 精确匹配
        if model_id in provider_pricing:
            return provider_pricing[model_id]
        
        # 通配符匹配
        if "*" in provider_pricing:
            return provider_pricing["*"]
        
        # 默认免费
        return {"input": 0.0, "output": 0.0}
    
    def _calculate_cost(
        self,
        provider_id: str,
        model_id: str,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> float:
        """计算费用"""
        pricing = self._get_pricing(provider_id, model_id)
        input_cost = (prompt_tokens / 1000) * pricing.get("input", 0)
        output_cost = (completion_tokens / 1000) * pricing.get("output", 0)
        return input_cost + output_cost
    
    def record_usage(
        self,
        provider_id: str,
        model_id: str,
        prompt_tokens: int,
        completion_tokens: int,
        latency_ms: int,
        success: bool = True,
        error: str | None = None,
    ) -> UsageRecord:
        """
        记录一次调用。
        
        Args:
            provider_id: 厂商 ID
            model_id: 模型 ID
            prompt_tokens: 输入 token 数
            completion_tokens: 输出 token 数
            latency_ms: 延迟（毫秒）
            success: 是否成功
            error: 错误信息
        
        Returns:
            记录对象
        """
        total_tokens = prompt_tokens + completion_tokens
        cost_usd = self._calculate_cost(provider_id, model_id, prompt_tokens, completion_tokens)
        
        record = UsageRecord(
            timestamp=datetime.now(),
            provider_id=provider_id,
            model_id=model_id,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            success=success,
            error=error,
        )
        
        with self._lock:
            self._records.append(record)
        
        logger.debug(
            f"记录用量: {provider_id}/{model_id} "
            f"tokens={total_tokens} cost=${cost_usd:.6f} latency={latency_ms}ms"
        )
        
        return record
    
    def get_summary(self) -> CostSummary:
        """获取成本汇总"""
        with self._lock:
            records = list(self._records)
        
        summary = CostSummary()
        summary.total_calls = len(records)
        
        for r in records:
            if r.success:
                summary.successful_calls += 1
            else:
                summary.failed_calls += 1
            
            summary.total_prompt_tokens += r.prompt_tokens
            summary.total_completion_tokens += r.completion_tokens
            summary.total_tokens += r.total_tokens
            summary.total_cost_usd += r.cost_usd
            summary.total_latency_ms += r.latency_ms
            
            # 按厂商统计
            if r.provider_id not in summary.by_provider:
                summary.by_provider[r.provider_id] = {
                    "calls": 0, "tokens": 0, "cost_usd": 0.0
                }
            summary.by_provider[r.provider_id]["calls"] += 1
            summary.by_provider[r.provider_id]["tokens"] += r.total_tokens
            summary.by_provider[r.provider_id]["cost_usd"] += r.cost_usd
            
            # 按模型统计
            model_key = f"{r.provider_id}/{r.model_id}"
            if model_key not in summary.by_model:
                summary.by_model[model_key] = {
                    "calls": 0, "tokens": 0, "cost_usd": 0.0
                }
            summary.by_model[model_key]["calls"] += 1
            summary.by_model[model_key]["tokens"] += r.total_tokens
            summary.by_model[model_key]["cost_usd"] += r.cost_usd
        
        # 计算平均延迟
        if summary.successful_calls > 0:
            summary.avg_latency_ms = summary.total_latency_ms / summary.successful_calls
        
        return summary
    
    def get_records(self) -> list[UsageRecord]:
        """获取所有记录"""
        with self._lock:
            return list(self._records)
    
    def clear(self) -> None:
        """清空记录"""
        with self._lock:
            self._records.clear()
    
    def to_dict(self) -> dict[str, Any]:
        """转换为字典（用于序列化）"""
        summary = self.get_summary()
        return {
            "session_id": self.session_id,
            "total_calls": summary.total_calls,
            "successful_calls": summary.successful_calls,
            "failed_calls": summary.failed_calls,
            "total_tokens": summary.total_tokens,
            "total_cost_usd": round(summary.total_cost_usd, 6),
            "avg_latency_ms": round(summary.avg_latency_ms, 2),
            "by_provider": summary.by_provider,
            "by_model": summary.by_model,
        }


# ============================================================
# 全局实例
# ============================================================

_global_tracker: CostTracker | None = None
_tracker_lock = threading.Lock()


def get_cost_tracker() -> CostTracker:
    """获取全局成本追踪器"""
    global _global_tracker
    with _tracker_lock:
        if _global_tracker is None:
            _global_tracker = CostTracker()
        return _global_tracker


def reset_cost_tracker() -> None:
    """重置全局追踪器"""
    global _global_tracker
    with _tracker_lock:
        _global_tracker = None

