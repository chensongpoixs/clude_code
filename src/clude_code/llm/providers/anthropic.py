"""
Anthropic 厂商（Anthropic Provider）

Claude 系列模型支持。
注意：Anthropic 有自己的 API 格式，但也提供 OpenAI 兼容模式。
"""

from __future__ import annotations

from ..base import ModelInfo, ProviderConfig
from ..registry import ProviderRegistry
from .openai_compat import OpenAICompatProvider


@ProviderRegistry.register("anthropic")
class AnthropicProvider(OpenAICompatProvider):
    """
    Anthropic 厂商
    
    支持模型：claude-3-5-sonnet, claude-3-opus, claude-3-haiku 等
    
    注意：使用 OpenAI 兼容模式（通过代理或兼容层）
    """
    
    PROVIDER_NAME = "Anthropic"
    PROVIDER_ID = "anthropic"
    PROVIDER_TYPE = "cloud"
    REGION = "海外"
    
    MODELS = [
        ModelInfo(
            id="claude-3-5-sonnet-latest",
            name="Claude 3.5 Sonnet",
            provider="anthropic",
            context_window=200000,
            max_output_tokens=8192,
            supports_vision=True,
            pricing={"input": 0.003, "output": 0.015},
        ),
        ModelInfo(
            id="claude-3-5-haiku-latest",
            name="Claude 3.5 Haiku",
            provider="anthropic",
            context_window=200000,
            max_output_tokens=8192,
            supports_vision=True,
            pricing={"input": 0.0008, "output": 0.004},
        ),
        ModelInfo(
            id="claude-3-opus-latest",
            name="Claude 3 Opus",
            provider="anthropic",
            context_window=200000,
            max_output_tokens=4096,
            supports_vision=True,
            pricing={"input": 0.015, "output": 0.075},
        ),
        ModelInfo(
            id="claude-3-sonnet-20240229",
            name="Claude 3 Sonnet",
            provider="anthropic",
            context_window=200000,
            max_output_tokens=4096,
            supports_vision=True,
            pricing={"input": 0.003, "output": 0.015},
        ),
        ModelInfo(
            id="claude-3-haiku-20240307",
            name="Claude 3 Haiku",
            provider="anthropic",
            context_window=200000,
            max_output_tokens=4096,
            supports_vision=True,
            pricing={"input": 0.00025, "output": 0.00125},
        ),
    ]
    
    def __init__(self, config: ProviderConfig):
        if not config.base_url:
            # 使用 OpenAI 兼容代理（如 litellm proxy）
            config.base_url = "https://api.anthropic.com/v1"
        if not config.default_model:
            config.default_model = "claude-3-5-sonnet-latest"
        super().__init__(config)
    
    def list_models(self) -> list[ModelInfo]:
        return self.MODELS

