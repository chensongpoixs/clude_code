"""
月之暗面 Moonshot 厂商（Moonshot Provider）

Kimi 系列模型支持。
"""

from __future__ import annotations

from ..base import ModelInfo, ProviderConfig
from ..registry import ProviderRegistry
from .openai_compat import OpenAICompatProvider


@ProviderRegistry.register("moonshot")
class MoonshotProvider(OpenAICompatProvider):
    """
    月之暗面 厂商
    
    支持模型：moonshot-v1-8k, moonshot-v1-32k, moonshot-v1-128k 等
    """
    
    PROVIDER_NAME = "月之暗面 (Moonshot)"
    PROVIDER_ID = "moonshot"
    PROVIDER_TYPE = "cloud"
    REGION = "国内"
    
    MODELS = [
        ModelInfo(
            id="moonshot-v1-8k",
            name="Moonshot V1 8K",
            provider="moonshot",
            context_window=8192,
            max_output_tokens=4096,
            pricing={"input": 0.000012, "output": 0.000012},
        ),
        ModelInfo(
            id="moonshot-v1-32k",
            name="Moonshot V1 32K",
            provider="moonshot",
            context_window=32768,
            max_output_tokens=4096,
            pricing={"input": 0.000024, "output": 0.000024},
        ),
        ModelInfo(
            id="moonshot-v1-128k",
            name="Moonshot V1 128K",
            provider="moonshot",
            context_window=131072,
            max_output_tokens=4096,
            pricing={"input": 0.00006, "output": 0.00006},
        ),
        ModelInfo(
            id="kimi-latest",
            name="Kimi Latest",
            provider="moonshot",
            context_window=131072,
            max_output_tokens=4096,
        ),
    ]
    
    def __init__(self, config: ProviderConfig):
        if not config.base_url:
            config.base_url = "https://api.moonshot.cn/v1"
        if not config.default_model:
            config.default_model = "moonshot-v1-8k"
        super().__init__(config)
    
    def list_models(self) -> list[ModelInfo]:
        return self.MODELS

