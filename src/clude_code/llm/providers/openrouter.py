"""
OpenRouter 厂商（OpenRouter Provider）

OpenRouter 多模型聚合平台支持。
"""

from __future__ import annotations

from ..base import ModelInfo, ProviderConfig
from ..registry import ProviderRegistry
from .openai_compat import OpenAICompatProvider


@ProviderRegistry.register("openrouter")
class OpenRouterProvider(OpenAICompatProvider):
    """
    OpenRouter 厂商
    
    特点：聚合多个厂商的模型，统一 API
    """
    
    PROVIDER_NAME = "OpenRouter"
    PROVIDER_ID = "openrouter"
    PROVIDER_TYPE = "aggregator"
    REGION = "海外"
    
    MODELS = [
        # OpenAI 模型
        ModelInfo(
            id="openai/gpt-4o",
            name="GPT-4o (via OpenRouter)",
            provider="openrouter",
            context_window=128000,
            max_output_tokens=16384,
            supports_vision=True,
            supports_function_call=True,
        ),
        ModelInfo(
            id="openai/o1-preview",
            name="o1 Preview (via OpenRouter)",
            provider="openrouter",
            context_window=128000,
            max_output_tokens=32768,
        ),
        # Anthropic 模型
        ModelInfo(
            id="anthropic/claude-3.5-sonnet",
            name="Claude 3.5 Sonnet (via OpenRouter)",
            provider="openrouter",
            context_window=200000,
            max_output_tokens=8192,
            supports_vision=True,
        ),
        ModelInfo(
            id="anthropic/claude-3-opus",
            name="Claude 3 Opus (via OpenRouter)",
            provider="openrouter",
            context_window=200000,
            max_output_tokens=4096,
            supports_vision=True,
        ),
        # Google 模型
        ModelInfo(
            id="google/gemini-2.0-flash-exp:free",
            name="Gemini 2.0 Flash (Free)",
            provider="openrouter",
            context_window=1048576,
            max_output_tokens=8192,
            supports_vision=True,
        ),
        # DeepSeek
        ModelInfo(
            id="deepseek/deepseek-chat",
            name="DeepSeek Chat (via OpenRouter)",
            provider="openrouter",
            context_window=64000,
            max_output_tokens=8192,
        ),
        ModelInfo(
            id="deepseek/deepseek-r1",
            name="DeepSeek R1 (via OpenRouter)",
            provider="openrouter",
            context_window=64000,
            max_output_tokens=8192,
        ),
        # 免费模型
        ModelInfo(
            id="meta-llama/llama-3.2-3b-instruct:free",
            name="Llama 3.2 3B (Free)",
            provider="openrouter",
            context_window=131072,
            max_output_tokens=4096,
        ),
        ModelInfo(
            id="qwen/qwen-2.5-72b-instruct:free",
            name="Qwen 2.5 72B (Free)",
            provider="openrouter",
            context_window=32768,
            max_output_tokens=4096,
        ),
    ]
    
    def __init__(self, config: ProviderConfig):
        if not config.base_url:
            config.base_url = "https://openrouter.ai/api/v1"
        if not config.default_model:
            config.default_model = "deepseek/deepseek-chat"
        super().__init__(config)
    
    def list_models(self) -> list[ModelInfo]:
        return self.MODELS

