"""
百川智能 厂商（Baichuan Provider）

百川系列模型支持。
"""

from __future__ import annotations

from ..base import ModelInfo, ProviderConfig
from ..registry import ProviderRegistry
from .openai_compat import OpenAICompatProvider


@ProviderRegistry.register("baichuan")
class BaichuanProvider(OpenAICompatProvider):
    """
    百川智能 厂商
    
    支持模型：Baichuan4, Baichuan3-Turbo 等
    """
    
    PROVIDER_NAME = "百川智能 (Baichuan)"
    PROVIDER_ID = "baichuan"
    PROVIDER_TYPE = "cloud"
    REGION = "国内"
    
    MODELS = [
        ModelInfo(
            id="Baichuan4",
            name="Baichuan 4",
            provider="baichuan",
            context_window=32768,
            max_output_tokens=4096,
            supports_function_call=True,
            pricing={"input": 0.0001, "output": 0.0001},
        ),
        ModelInfo(
            id="Baichuan3-Turbo",
            name="Baichuan 3 Turbo",
            provider="baichuan",
            context_window=32768,
            max_output_tokens=4096,
            pricing={"input": 0.00001, "output": 0.00001},
        ),
        ModelInfo(
            id="Baichuan3-Turbo-128k",
            name="Baichuan 3 Turbo 128K",
            provider="baichuan",
            context_window=131072,
            max_output_tokens=4096,
            pricing={"input": 0.00002, "output": 0.00002},
        ),
        ModelInfo(
            id="Baichuan4-Turbo",
            name="Baichuan 4 Turbo",
            provider="baichuan",
            context_window=32768,
            max_output_tokens=4096,
            supports_function_call=True,
            pricing={"input": 0.00003, "output": 0.00003},
        ),
    ]
    
    def __init__(self, config: ProviderConfig):
        if not config.base_url:
            config.base_url = "https://api.baichuan-ai.com/v1"
        if not config.default_model:
            config.default_model = "Baichuan4"
        super().__init__(config)
    
    def list_models(self) -> list[ModelInfo]:
        return self.MODELS

