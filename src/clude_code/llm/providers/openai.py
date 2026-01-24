"""
OpenAI 厂商（OpenAI Provider）

官方 OpenAI API 支持。
"""

from __future__ import annotations

from ..base import ModelInfo, ProviderConfig
from ..registry import ProviderRegistry
from .openai_compat import OpenAICompatProvider


@ProviderRegistry.register("openai")
class OpenAIProvider(OpenAICompatProvider):
    """
    OpenAI 官方厂商
    
    支持模型：gpt-4o, gpt-4o-mini, o1-preview, o1-mini 等
    """
    
    PROVIDER_NAME = "OpenAI"
    PROVIDER_ID = "openai"
    PROVIDER_TYPE = "cloud"
    REGION = "海外"
    
    # 官方模型列表
    MODELS = [
        ModelInfo(
            id="gpt-4o",
            name="GPT-4o",
            provider="openai",
            context_window=128000,
            max_output_tokens=16384,
            supports_vision=True,
            supports_function_call=True,
            pricing={"input": 0.0025, "output": 0.01},
        ),
        ModelInfo(
            id="gpt-4o-mini",
            name="GPT-4o Mini",
            provider="openai",
            context_window=128000,
            max_output_tokens=16384,
            supports_vision=True,
            supports_function_call=True,
            pricing={"input": 0.00015, "output": 0.0006},
        ),
        ModelInfo(
            id="gpt-4-turbo",
            name="GPT-4 Turbo",
            provider="openai",
            context_window=128000,
            max_output_tokens=4096,
            supports_vision=True,
            supports_function_call=True,
            pricing={"input": 0.01, "output": 0.03},
        ),
        ModelInfo(
            id="gpt-4",
            name="GPT-4",
            provider="openai",
            context_window=8192,
            max_output_tokens=8192,
            supports_function_call=True,
            pricing={"input": 0.03, "output": 0.06},
        ),
        ModelInfo(
            id="gpt-3.5-turbo",
            name="GPT-3.5 Turbo",
            provider="openai",
            context_window=16385,
            max_output_tokens=4096,
            supports_function_call=True,
            pricing={"input": 0.0005, "output": 0.0015},
        ),
        ModelInfo(
            id="o1-preview",
            name="o1 Preview",
            provider="openai",
            context_window=128000,
            max_output_tokens=32768,
            supports_streaming=False,
            pricing={"input": 0.015, "output": 0.06},
        ),
        ModelInfo(
            id="o1-mini",
            name="o1 Mini",
            provider="openai",
            context_window=128000,
            max_output_tokens=65536,
            supports_streaming=False,
            pricing={"input": 0.003, "output": 0.012},
        ),
    ]
    
    def __init__(self, config: ProviderConfig):
        # 设置默认 base_url
        if not config.base_url:
            config.base_url = "https://api.openai.com/v1"
        if not config.default_model:
            config.default_model = "gpt-4o"
        super().__init__(config)
    
    def list_models(self) -> list[ModelInfo]:
        """返回官方模型列表"""
        return self.MODELS

