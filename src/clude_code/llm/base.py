"""
LLM 厂商抽象基类（LLM Provider Abstract Base Class）

定义所有 LLM 厂商必须实现的统一接口。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Iterator, TYPE_CHECKING

if TYPE_CHECKING:
    from .llama_cpp_http import ChatMessage


@dataclass
class ModelInfo:
    """
    模型元信息（Model Metadata）
    
    描述单个 LLM 模型的能力和限制。
    """
    id: str
    name: str
    provider: str = ""  # 厂商 ID，可选（由 Provider 自动填充）
    context_window: int = 4096
    max_output_tokens: int = 4096
    supports_vision: bool = False
    supports_function_call: bool = False
    supports_streaming: bool = True
    pricing: dict[str, float] | None = None  # {"input": 0.001, "output": 0.002} per 1K tokens
    
    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "name": self.name,
            "provider": self.provider,
            "context_window": self.context_window,
            "max_output_tokens": self.max_output_tokens,
            "supports_vision": self.supports_vision,
            "supports_function_call": self.supports_function_call,
            "supports_streaming": self.supports_streaming,
            "pricing": self.pricing,
        }


@dataclass
class ProviderConfig:
    """
    厂商配置（Provider Configuration）
    
    存储单个厂商的连接和认证信息。
    """
    name: str
    api_key: str = ""
    base_url: str = ""
    api_version: str = ""
    organization: str = ""
    default_model: str = ""
    timeout_s: int = 120
    extra: dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        """转换为字典（隐藏敏感信息）"""
        return {
            "name": self.name,
            "api_key": f"{self.api_key[:8]}..." if self.api_key else "",
            "base_url": self.base_url,
            "api_version": self.api_version,
            "default_model": self.default_model,
        }


class LLMProvider(ABC):
    """
    LLM 厂商抽象基类
    
    所有厂商实现必须继承此类并实现抽象方法。
    
    类属性：
        PROVIDER_NAME: 厂商显示名称（如 "OpenAI"）
        PROVIDER_ID: 厂商标识符（如 "openai"）
        PROVIDER_TYPE: 厂商类型（cloud | local | aggregator）
        REGION: 区域（海外 | 国内 | 通用）
    """
    
    # 子类必须覆盖这些属性
    PROVIDER_NAME: str = "Unknown"
    PROVIDER_ID: str = "unknown"
    PROVIDER_TYPE: str = "cloud"  # cloud | local | aggregator
    REGION: str = "通用"           # 海外 | 国内 | 通用
    
    def __init__(self, config: ProviderConfig):
        """
        初始化厂商。
        
        Args:
            config: 厂商配置
        """
        self.config = config
        self._current_model: str = config.default_model
    
    @property
    def current_model(self) -> str:
        """当前使用的模型"""
        return self._current_model
    
    @current_model.setter
    def current_model(self, model: str) -> None:
        """设置当前模型"""
        self._current_model = model
    
    # ========== 抽象方法（子类必须实现） ==========
    
    @abstractmethod
    def chat(
        self,
        messages: list["ChatMessage"],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> str:
        """
        同步聊天。
        
        Args:
            messages: 消息列表
            model: 模型 ID（None 使用默认）
            temperature: 温度
            max_tokens: 最大输出 token
            **kwargs: 厂商特定参数
        
        Returns:
            助手回复文本
        """
        pass
    
    @abstractmethod
    async def chat_async(
        self,
        messages: list["ChatMessage"],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> str:
        """
        异步聊天。
        
        Args:
            messages: 消息列表
            model: 模型 ID（None 使用默认）
            temperature: 温度
            max_tokens: 最大输出 token
            **kwargs: 厂商特定参数
        
        Returns:
            助手回复文本
        """
        pass
    
    @abstractmethod
    def chat_stream(
        self,
        messages: list["ChatMessage"],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> Iterator[str]:
        """
        流式聊天。
        
        Args:
            messages: 消息列表
            model: 模型 ID（None 使用默认）
            temperature: 温度
            max_tokens: 最大输出 token
            **kwargs: 厂商特定参数
        
        Yields:
            助手回复文本片段
        """
        pass
    
    @abstractmethod
    def list_models(self) -> list[ModelInfo]:
        """
        获取可用模型列表。
        
        Returns:
            模型信息列表
        """
        pass
    
    # ========== 可选方法（带默认实现） ==========
    
    def get_model_info(self, model_id: str) -> ModelInfo | None:
        """
        获取单个模型信息。
        
        Args:
            model_id: 模型 ID
        
        Returns:
            模型信息，不存在返回 None
        """
        for model in self.list_models():
            if model.id == model_id:
                return model
        return None
    
    def validate_config(self) -> tuple[bool, str]:
        """
        验证配置有效性。
        
        Returns:
            (是否有效, 消息)
        """
        if not self.config.name:
            return False, "厂商名称不能为空"
        return True, "配置有效"
    
    def test_connection(self) -> tuple[bool, str]:
        """
        测试连接。
        
        Returns:
            (是否成功, 消息)
        """
        try:
            models = self.list_models()
            if models:
                return True, f"连接成功，可用模型: {len(models)} 个"
            return True, "连接成功，但未获取到模型列表"
        except Exception as e:
            return False, f"连接失败: {e}"
    
    def get_provider_info(self) -> dict[str, Any]:
        """
        获取厂商信息。
        
        Returns:
            厂商信息字典
        """
        return {
            "name": self.PROVIDER_NAME,
            "id": self.PROVIDER_ID,
            "type": self.PROVIDER_TYPE,
            "region": self.REGION,
            "current_model": self.current_model,
            "config": self.config.to_dict(),
        }

