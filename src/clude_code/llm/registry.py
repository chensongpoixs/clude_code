"""
厂商注册表（Provider Registry）

管理所有 LLM 厂商的注册和实例化。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Type

if TYPE_CHECKING:
    from .base import LLMProvider, ProviderConfig

logger = logging.getLogger(__name__)


class ProviderRegistry:
    """
    厂商注册表（单例）
    
    功能：
    1. 注册厂商类（通过装饰器）
    2. 获取厂商实例（带缓存）
    3. 列出所有已注册厂商
    
    使用示例：
        # 注册厂商
        @ProviderRegistry.register("openai")
        class OpenAIProvider(LLMProvider):
            ...
        
        # 获取实例
        provider = ProviderRegistry.get_provider("openai", config)
    """
    
    _instance: "ProviderRegistry | None" = None
    _providers: dict[str, Type["LLMProvider"]] = {}
    _instances: dict[str, "LLMProvider"] = {}
    
    def __new__(cls) -> "ProviderRegistry":
        """单例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    @classmethod
    def register(cls, provider_id: str):
        """
        装饰器：注册厂商类。
        
        Args:
            provider_id: 厂商标识符（如 "openai"）
        
        示例：
            @ProviderRegistry.register("openai")
            class OpenAIProvider(LLMProvider):
                ...
        """
        def decorator(provider_class: Type["LLMProvider"]):
            if provider_id in cls._providers:
                logger.warning(f"厂商 '{provider_id}' 已注册，将被覆盖")
            cls._providers[provider_id] = provider_class
            logger.debug(f"已注册厂商: {provider_id} -> {provider_class.__name__}")
            return provider_class
        return decorator
    
    @classmethod
    def get_provider(
        cls,
        provider_id: str,
        config: "ProviderConfig",
        *,
        force_new: bool = False,
    ) -> "LLMProvider":
        """
        获取厂商实例。
        
        Args:
            provider_id: 厂商标识符
            config: 厂商配置
            force_new: 是否强制创建新实例
        
        Returns:
            厂商实例
        
        Raises:
            ValueError: 厂商未注册
        """
        if provider_id not in cls._providers:
            available = ", ".join(cls._providers.keys()) or "无"
            raise ValueError(f"未知厂商: '{provider_id}'。可用厂商: {available}")
        
        # 缓存键：厂商ID + API Key 前缀（支持同厂商多账号）
        cache_key = f"{provider_id}:{config.api_key[:8] if config.api_key else 'default'}"
        
        if not force_new and cache_key in cls._instances:
            logger.debug(f"使用缓存的厂商实例: {cache_key}")
            return cls._instances[cache_key]
        
        # 创建新实例
        provider_class = cls._providers[provider_id]
        instance = provider_class(config)
        cls._instances[cache_key] = instance
        logger.info(f"创建厂商实例: {provider_id} ({provider_class.PROVIDER_NAME})")
        
        return instance
    
    @classmethod
    def has_provider(cls, provider_id: str) -> bool:
        """
        检查厂商是否已注册。
        
        Args:
            provider_id: 厂商标识符
        
        Returns:
            是否已注册
        """
        return provider_id in cls._providers
    
    @classmethod
    def list_providers(cls) -> list[dict]:
        """
        列出所有已注册厂商。
        
        Returns:
            厂商信息列表
        """
        result = []
        for provider_id, provider_class in cls._providers.items():
            result.append({
                "id": provider_id,
                "name": provider_class.PROVIDER_NAME,
                "type": provider_class.PROVIDER_TYPE,
                "region": provider_class.REGION,
            })
        return result
    
    @classmethod
    def get_provider_class(cls, provider_id: str) -> Type["LLMProvider"] | None:
        """
        获取厂商类（不实例化）。
        
        Args:
            provider_id: 厂商标识符
        
        Returns:
            厂商类，不存在返回 None
        """
        return cls._providers.get(provider_id)
    
    @classmethod
    def clear_instances(cls) -> None:
        """清除所有缓存的实例"""
        cls._instances.clear()
        logger.debug("已清除所有厂商实例缓存")
    
    @classmethod
    def clear_all(cls) -> None:
        """清除所有注册和实例（用于测试）"""
        cls._providers.clear()
        cls._instances.clear()
        logger.debug("已清除所有厂商注册和实例")


# ============================================================
# 便捷函数
# ============================================================

def get_provider(provider_id: str, config: "ProviderConfig") -> "LLMProvider":
    """便捷函数：获取厂商实例"""
    return ProviderRegistry.get_provider(provider_id, config)


def list_providers() -> list[dict]:
    """便捷函数：列出所有厂商"""
    return ProviderRegistry.list_providers()


def has_provider(provider_id: str) -> bool:
    """便捷函数：检查厂商是否存在"""
    return ProviderRegistry.has_provider(provider_id)

