"""
MiniMax 厂商（MiniMax Provider）

MiniMax 系列模型支持。
"""

from __future__ import annotations

from ..base import ModelInfo, ProviderConfig
from ..registry import ProviderRegistry
from .openai_compat import OpenAICompatProvider


@ProviderRegistry.register("minimax")
class MiniMaxProvider(OpenAICompatProvider):
    """
    MiniMax 厂商
    
    支持模型：abab6.5s, abab6.5g 等
    """
    
    PROVIDER_NAME = "MiniMax"
    PROVIDER_ID = "minimax"
    PROVIDER_TYPE = "cloud"
    REGION = "国内"
    
    MODELS = [
        ModelInfo(
            id="abab6.5s-chat",
            name="ABAB 6.5S Chat",
            provider="minimax",
            context_window=245760,
            max_output_tokens=8192,
            supports_function_call=True,
            pricing={"input": 0.000001, "output": 0.000002},
        ),
        ModelInfo(
            id="abab6.5g-chat",
            name="ABAB 6.5G Chat",
            provider="minimax",
            context_window=8192,
            max_output_tokens=4096,
            pricing={"input": 0.000005, "output": 0.000005},
        ),
        ModelInfo(
            id="abab6.5t-chat",
            name="ABAB 6.5T Chat",
            provider="minimax",
            context_window=8192,
            max_output_tokens=4096,
            pricing={"input": 0.00001, "output": 0.00001},
        ),
    ]
    
    def __init__(self, config: ProviderConfig):
        if not config.base_url:
            config.base_url = "https://api.minimax.chat/v1"
        if not config.default_model:
            config.default_model = "abab6.5s-chat"
        super().__init__(config)
    
    def list_models(self) -> list[ModelInfo]:
        return self.MODELS

