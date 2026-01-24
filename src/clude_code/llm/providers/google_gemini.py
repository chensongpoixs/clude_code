"""
Google Gemini 厂商（Google Gemini Provider）

Gemini 系列模型支持。
"""

from __future__ import annotations

from ..base import ModelInfo, ProviderConfig
from ..registry import ProviderRegistry
from .openai_compat import OpenAICompatProvider


@ProviderRegistry.register("google_gemini")
class GoogleGeminiProvider(OpenAICompatProvider):
    """
    Google Gemini 厂商
    
    支持模型：gemini-1.5-pro, gemini-1.5-flash, gemini-2.0-flash 等
    """
    
    PROVIDER_NAME = "Google Gemini"
    PROVIDER_ID = "google_gemini"
    PROVIDER_TYPE = "cloud"
    REGION = "海外"
    
    MODELS = [
        ModelInfo(
            id="gemini-2.0-flash-exp",
            name="Gemini 2.0 Flash",
            provider="google_gemini",
            context_window=1048576,
            max_output_tokens=8192,
            supports_vision=True,
            supports_function_call=True,
        ),
        ModelInfo(
            id="gemini-1.5-pro",
            name="Gemini 1.5 Pro",
            provider="google_gemini",
            context_window=2097152,
            max_output_tokens=8192,
            supports_vision=True,
            supports_function_call=True,
            pricing={"input": 0.00125, "output": 0.005},
        ),
        ModelInfo(
            id="gemini-1.5-flash",
            name="Gemini 1.5 Flash",
            provider="google_gemini",
            context_window=1048576,
            max_output_tokens=8192,
            supports_vision=True,
            supports_function_call=True,
            pricing={"input": 0.000075, "output": 0.0003},
        ),
        ModelInfo(
            id="gemini-1.5-flash-8b",
            name="Gemini 1.5 Flash 8B",
            provider="google_gemini",
            context_window=1048576,
            max_output_tokens=8192,
            supports_vision=True,
            pricing={"input": 0.0000375, "output": 0.00015},
        ),
    ]
    
    def __init__(self, config: ProviderConfig):
        if not config.base_url:
            config.base_url = "https://generativelanguage.googleapis.com/v1beta/openai"
        if not config.default_model:
            config.default_model = "gemini-1.5-pro"
        super().__init__(config)
    
    def list_models(self) -> list[ModelInfo]:
        return self.MODELS

