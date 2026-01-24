"""
Groq 厂商（Groq Provider）

Groq 超快推理平台支持。
"""

from __future__ import annotations

from ..base import ModelInfo, ProviderConfig
from ..registry import ProviderRegistry
from .openai_compat import OpenAICompatProvider


@ProviderRegistry.register("groq")
class GroqProvider(OpenAICompatProvider):
    """
    Groq 厂商
    
    特点：超快推理速度（LPU 加速）
    """
    
    PROVIDER_NAME = "Groq"
    PROVIDER_ID = "groq"
    PROVIDER_TYPE = "cloud"
    REGION = "海外"
    
    MODELS = [
        ModelInfo(
            id="llama-3.3-70b-versatile",
            name="Llama 3.3 70B",
            provider="groq",
            context_window=131072,
            max_output_tokens=32768,
            supports_function_call=True,
        ),
        ModelInfo(
            id="llama-3.1-70b-versatile",
            name="Llama 3.1 70B",
            provider="groq",
            context_window=131072,
            max_output_tokens=8192,
            supports_function_call=True,
        ),
        ModelInfo(
            id="llama-3.1-8b-instant",
            name="Llama 3.1 8B Instant",
            provider="groq",
            context_window=131072,
            max_output_tokens=8192,
        ),
        ModelInfo(
            id="mixtral-8x7b-32768",
            name="Mixtral 8x7B",
            provider="groq",
            context_window=32768,
            max_output_tokens=4096,
            supports_function_call=True,
        ),
        ModelInfo(
            id="gemma2-9b-it",
            name="Gemma 2 9B",
            provider="groq",
            context_window=8192,
            max_output_tokens=4096,
        ),
        ModelInfo(
            id="deepseek-r1-distill-llama-70b",
            name="DeepSeek R1 Distill 70B",
            provider="groq",
            context_window=131072,
            max_output_tokens=16384,
        ),
    ]
    
    def __init__(self, config: ProviderConfig):
        if not config.base_url:
            config.base_url = "https://api.groq.com/openai/v1"
        if not config.default_model:
            config.default_model = "llama-3.3-70b-versatile"
        super().__init__(config)
    
    def list_models(self) -> list[ModelInfo]:
        return self.MODELS

