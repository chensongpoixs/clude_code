"""
Mistral AI 厂商（Mistral Provider）

Mistral 系列模型支持。
"""

from __future__ import annotations

from ..base import ModelInfo, ProviderConfig
from ..registry import ProviderRegistry
from .openai_compat import OpenAICompatProvider


@ProviderRegistry.register("mistral")
class MistralProvider(OpenAICompatProvider):
    """
    Mistral AI 厂商
    
    支持模型：mistral-large, mistral-small, codestral 等
    """
    
    PROVIDER_NAME = "Mistral AI"
    PROVIDER_ID = "mistral"
    PROVIDER_TYPE = "cloud"
    REGION = "海外"
    
    MODELS = [
        ModelInfo(
            id="mistral-large-latest",
            name="Mistral Large",
            provider="mistral",
            context_window=131072,
            max_output_tokens=8192,
            supports_function_call=True,
            pricing={"input": 0.002, "output": 0.006},
        ),
        ModelInfo(
            id="mistral-small-latest",
            name="Mistral Small",
            provider="mistral",
            context_window=131072,
            max_output_tokens=8192,
            supports_function_call=True,
            pricing={"input": 0.0002, "output": 0.0006},
        ),
        ModelInfo(
            id="codestral-latest",
            name="Codestral",
            provider="mistral",
            context_window=32768,
            max_output_tokens=8192,
            pricing={"input": 0.0002, "output": 0.0006},
        ),
        ModelInfo(
            id="pixtral-large-latest",
            name="Pixtral Large",
            provider="mistral",
            context_window=131072,
            max_output_tokens=8192,
            supports_vision=True,
            pricing={"input": 0.002, "output": 0.006},
        ),
        ModelInfo(
            id="ministral-8b-latest",
            name="Ministral 8B",
            provider="mistral",
            context_window=131072,
            max_output_tokens=8192,
            pricing={"input": 0.0001, "output": 0.0001},
        ),
        ModelInfo(
            id="open-mixtral-8x22b",
            name="Mixtral 8x22B",
            provider="mistral",
            context_window=65536,
            max_output_tokens=8192,
            supports_function_call=True,
            pricing={"input": 0.002, "output": 0.006},
        ),
    ]
    
    def __init__(self, config: ProviderConfig):
        if not config.base_url:
            config.base_url = "https://api.mistral.ai/v1"
        if not config.default_model:
            config.default_model = "mistral-small-latest"
        super().__init__(config)
    
    def list_models(self) -> list[ModelInfo]:
        return self.MODELS

