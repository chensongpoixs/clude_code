"""
故障转移模块（Failover）

功能：
1. 当主厂商请求失败时自动切换到备用厂商
2. 支持配置优先级列表
3. 记录失败原因和切换历史
4. 支持健康检查

设计原则：
- 透明切换，上层无感知
- 可配置的重试策略
- 完整的日志记录
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from .base import LLMProvider
    from .llama_cpp_http import ChatMessage

logger = logging.getLogger(__name__)


@dataclass
class FailoverEvent:
    """故障转移事件"""
    timestamp: datetime
    from_provider: str
    to_provider: str
    error_type: str
    error_message: str
    retry_count: int


@dataclass
class ProviderHealth:
    """厂商健康状态"""
    provider_id: str
    is_healthy: bool = True
    last_success: datetime | None = None
    last_failure: datetime | None = None
    consecutive_failures: int = 0
    total_failures: int = 0
    total_successes: int = 0
    
    def record_success(self) -> None:
        """记录成功"""
        self.is_healthy = True
        self.last_success = datetime.now()
        self.consecutive_failures = 0
        self.total_successes += 1
    
    def record_failure(self) -> None:
        """记录失败"""
        self.last_failure = datetime.now()
        self.consecutive_failures += 1
        self.total_failures += 1
        # 连续失败 3 次标记为不健康
        if self.consecutive_failures >= 3:
            self.is_healthy = False


@dataclass
class FailoverConfig:
    """故障转移配置"""
    enabled: bool = True
    max_retries: int = 2
    retry_delay_ms: int = 500
    fallback_chain: list[str] = field(default_factory=list)
    # 健康检查间隔（秒）
    health_check_interval: int = 60
    # 不健康厂商恢复时间（秒）
    recovery_time: int = 300


class FailoverManager:
    """
    故障转移管理器
    
    用法：
        failover = FailoverManager(config)
        failover.register_provider("openai", openai_provider)
        failover.register_provider("deepseek", deepseek_provider)
        
        result = failover.chat_with_failover(messages)
    """
    
    def __init__(self, config: FailoverConfig | None = None):
        self.config = config or FailoverConfig()
        self._providers: dict[str, "LLMProvider"] = {}
        self._health: dict[str, ProviderHealth] = {}
        self._events: list[FailoverEvent] = []
        self._primary_provider: str = ""
    
    def register_provider(
        self,
        provider_id: str,
        provider: "LLMProvider",
        *,
        is_primary: bool = False,
    ) -> None:
        """
        注册厂商。
        
        Args:
            provider_id: 厂商 ID
            provider: 厂商实例
            is_primary: 是否为主厂商
        """
        self._providers[provider_id] = provider
        self._health[provider_id] = ProviderHealth(provider_id=provider_id)
        
        if is_primary or not self._primary_provider:
            self._primary_provider = provider_id
        
        logger.debug(f"注册故障转移厂商: {provider_id} (primary={is_primary})")
    
    def set_primary(self, provider_id: str) -> None:
        """设置主厂商"""
        if provider_id not in self._providers:
            raise ValueError(f"厂商未注册: {provider_id}")
        self._primary_provider = provider_id
    
    def get_fallback_chain(self) -> list[str]:
        """
        获取故障转移链。
        
        优先使用配置的链，否则按注册顺序（主厂商优先）。
        """
        if self.config.fallback_chain:
            # 过滤出已注册的厂商
            return [p for p in self.config.fallback_chain if p in self._providers]
        
        # 默认：主厂商 + 其他厂商
        chain = [self._primary_provider] if self._primary_provider else []
        for pid in self._providers:
            if pid not in chain:
                chain.append(pid)
        return chain
    
    def _should_skip_provider(self, provider_id: str) -> bool:
        """检查是否应该跳过此厂商"""
        health = self._health.get(provider_id)
        if not health:
            return False
        
        # 如果不健康，检查是否已恢复
        if not health.is_healthy and health.last_failure:
            elapsed = (datetime.now() - health.last_failure).total_seconds()
            if elapsed >= self.config.recovery_time:
                # 恢复尝试
                health.is_healthy = True
                health.consecutive_failures = 0
                logger.info(f"厂商 {provider_id} 已恢复，重新尝试")
                return False
            return True
        
        return False
    
    def chat_with_failover(
        self,
        messages: list["ChatMessage"],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        on_failover: Callable[[FailoverEvent], None] | None = None,
        **kwargs: Any,
    ) -> str:
        """
        带故障转移的聊天。
        
        Args:
            messages: 消息列表
            model: 模型 ID（可选）
            temperature: 温度
            max_tokens: 最大输出 token
            on_failover: 故障转移回调
            **kwargs: 其他参数
        
        Returns:
            助手回复
        
        Raises:
            AllProvidersFailedError: 所有厂商都失败
        """
        if not self.config.enabled:
            # 未启用故障转移，直接使用主厂商
            provider = self._providers.get(self._primary_provider)
            if not provider:
                raise ValueError("未设置主厂商")
            return provider.chat(messages, model=model, temperature=temperature, max_tokens=max_tokens, **kwargs)
        
        chain = self.get_fallback_chain()
        last_error: Exception | None = None
        retry_count = 0
        
        for provider_id in chain:
            if self._should_skip_provider(provider_id):
                logger.debug(f"跳过不健康的厂商: {provider_id}")
                continue
            
            provider = self._providers[provider_id]
            health = self._health[provider_id]
            
            for attempt in range(self.config.max_retries + 1):
                try:
                    start_time = time.time()
                    result = provider.chat(
                        messages,
                        model=model,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        **kwargs,
                    )
                    latency_ms = int((time.time() - start_time) * 1000)
                    
                    # 记录成功
                    health.record_success()
                    logger.debug(f"厂商 {provider_id} 请求成功，延迟 {latency_ms}ms")
                    
                    return result
                    
                except Exception as e:
                    last_error = e
                    health.record_failure()
                    retry_count += 1
                    
                    logger.warning(
                        f"厂商 {provider_id} 请求失败 (尝试 {attempt + 1}/{self.config.max_retries + 1}): {e}"
                    )
                    
                    if attempt < self.config.max_retries:
                        time.sleep(self.config.retry_delay_ms / 1000)
            
            # 当前厂商所有重试都失败，记录故障转移事件
            next_provider = None
            for pid in chain:
                if pid != provider_id and not self._should_skip_provider(pid):
                    next_provider = pid
                    break
            
            if next_provider:
                event = FailoverEvent(
                    timestamp=datetime.now(),
                    from_provider=provider_id,
                    to_provider=next_provider,
                    error_type=type(last_error).__name__ if last_error else "Unknown",
                    error_message=str(last_error) if last_error else "",
                    retry_count=retry_count,
                )
                self._events.append(event)
                
                if on_failover:
                    on_failover(event)
                
                logger.info(f"故障转移: {provider_id} → {next_provider}")
        
        # 所有厂商都失败
        raise AllProvidersFailedError(
            f"所有厂商都失败。尝试了 {len(chain)} 个厂商，共 {retry_count} 次请求。"
            f"最后错误: {last_error}"
        )
    
    def get_health_status(self) -> dict[str, dict[str, Any]]:
        """获取所有厂商的健康状态"""
        return {
            pid: {
                "is_healthy": h.is_healthy,
                "consecutive_failures": h.consecutive_failures,
                "total_failures": h.total_failures,
                "total_successes": h.total_successes,
                "last_success": h.last_success.isoformat() if h.last_success else None,
                "last_failure": h.last_failure.isoformat() if h.last_failure else None,
            }
            for pid, h in self._health.items()
        }
    
    def get_events(self) -> list[FailoverEvent]:
        """获取故障转移事件历史"""
        return list(self._events)
    
    def reset_health(self, provider_id: str | None = None) -> None:
        """重置健康状态"""
        if provider_id:
            if provider_id in self._health:
                self._health[provider_id] = ProviderHealth(provider_id=provider_id)
        else:
            for pid in self._health:
                self._health[pid] = ProviderHealth(provider_id=pid)


class AllProvidersFailedError(Exception):
    """所有厂商都失败的异常"""
    pass

