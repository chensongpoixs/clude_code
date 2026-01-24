"""
DeepSeek 厂商（DeepSeek Provider）

DeepSeek 系列模型支持。
"""

from __future__ import annotations

from ..base import ModelInfo, ProviderConfig
from ..registry import ProviderRegistry
from .openai_compat import OpenAICompatProvider


@ProviderRegistry.register("deepseek")
class DeepSeekProvider(OpenAICompatProvider):
    """
    DeepSeek 厂商
    
    支持模型：deepseek-chat, deepseek-coder, deepseek-reasoner 等
    """
    
    PROVIDER_NAME = "DeepSeek"
    PROVIDER_ID = "deepseek"
    PROVIDER_TYPE = "cloud"
    REGION = "国内"
    
    MODELS = [
        ModelInfo(
            id="deepseek-chat",
            name="DeepSeek Chat (V3)",
            provider="deepseek",
            context_window=64000,
            max_output_tokens=8192,
            supports_function_call=True,
            pricing={"input": 0.00014, "output": 0.00028},
        ),
        ModelInfo(
            id="deepseek-reasoner",
            name="DeepSeek R1",
            provider="deepseek",
            context_window=64000,
            max_output_tokens=8192,
            pricing={"input": 0.00055, "output": 0.00219},
        ),
        ModelInfo(
            id="deepseek-coder",
            name="DeepSeek Coder",
            provider="deepseek",
            context_window=64000,
            max_output_tokens=8192,
            supports_function_call=True,
            pricing={"input": 0.00014, "output": 0.00028},
        ),
    ]
    
    def __init__(self, config: ProviderConfig):
        if not config.base_url:
            config.base_url = "https://api.deepseek.com/v1"
        if not config.default_model:
            config.default_model = "deepseek-chat"
        super().__init__(config)
    
    def list_models(self) -> list[ModelInfo]:
        return self.MODELS

