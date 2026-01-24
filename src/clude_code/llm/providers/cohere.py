"""
Cohere 厂商（Cohere Provider）

Cohere 系列模型支持。
"""

from __future__ import annotations

from ..base import ModelInfo, ProviderConfig
from ..registry import ProviderRegistry
from .openai_compat import OpenAICompatProvider


@ProviderRegistry.register("cohere")
class CohereProvider(OpenAICompatProvider):
    """
    Cohere 厂商
    
    支持模型：command-r, command-r-plus 等
    """
    
    PROVIDER_NAME = "Cohere"
    PROVIDER_ID = "cohere"
    PROVIDER_TYPE = "cloud"
    REGION = "海外"
    
    MODELS = [
        ModelInfo(
            id="command-r-plus",
            name="Command R+",
            provider="cohere",
            context_window=128000,
            max_output_tokens=4096,
            supports_function_call=True,
            pricing={"input": 0.0025, "output": 0.01},
        ),
        ModelInfo(
            id="command-r",
            name="Command R",
            provider="cohere",
            context_window=128000,
            max_output_tokens=4096,
            supports_function_call=True,
            pricing={"input": 0.00015, "output": 0.0006},
        ),
        ModelInfo(
            id="command-light",
            name="Command Light",
            provider="cohere",
            context_window=4096,
            max_output_tokens=4096,
            pricing={"input": 0.000015, "output": 0.000015},
        ),
        ModelInfo(
            id="command-nightly",
            name="Command Nightly",
            provider="cohere",
            context_window=128000,
            max_output_tokens=4096,
        ),
    ]
    
    def __init__(self, config: ProviderConfig):
        if not config.base_url:
            config.base_url = "https://api.cohere.ai/v1"
        if not config.default_model:
            config.default_model = "command-r"
        super().__init__(config)
    
    def list_models(self) -> list[ModelInfo]:
        return self.MODELS

