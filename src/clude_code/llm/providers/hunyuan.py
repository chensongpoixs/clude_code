"""
腾讯混元 厂商（Hunyuan Provider）

腾讯混元系列模型支持。
"""

from __future__ import annotations

from ..base import ModelInfo, ProviderConfig
from ..registry import ProviderRegistry
from .openai_compat import OpenAICompatProvider


@ProviderRegistry.register("hunyuan")
class HunyuanProvider(OpenAICompatProvider):
    """
    腾讯混元 厂商
    
    支持模型：hunyuan-lite, hunyuan-standard, hunyuan-pro 等
    """
    
    PROVIDER_NAME = "腾讯混元"
    PROVIDER_ID = "hunyuan"
    PROVIDER_TYPE = "cloud"
    REGION = "国内"
    
    MODELS = [
        ModelInfo(
            id="hunyuan-pro",
            name="Hunyuan Pro",
            provider="hunyuan",
            context_window=32768,
            max_output_tokens=4096,
            supports_function_call=True,
            pricing={"input": 0.00003, "output": 0.0001},
        ),
        ModelInfo(
            id="hunyuan-standard",
            name="Hunyuan Standard",
            provider="hunyuan",
            context_window=32768,
            max_output_tokens=2048,
            pricing={"input": 0.0000045, "output": 0.000005},
        ),
        ModelInfo(
            id="hunyuan-standard-256K",
            name="Hunyuan Standard 256K",
            provider="hunyuan",
            context_window=262144,
            max_output_tokens=6144,
            pricing={"input": 0.000015, "output": 0.00006},
        ),
        ModelInfo(
            id="hunyuan-lite",
            name="Hunyuan Lite",
            provider="hunyuan",
            context_window=32768,
            max_output_tokens=2048,
            pricing={"input": 0.0, "output": 0.0},  # 免费
        ),
        ModelInfo(
            id="hunyuan-vision",
            name="Hunyuan Vision",
            provider="hunyuan",
            context_window=8192,
            max_output_tokens=4096,
            supports_vision=True,
            pricing={"input": 0.00018, "output": 0.00018},
        ),
    ]
    
    def __init__(self, config: ProviderConfig):
        if not config.base_url:
            config.base_url = "https://api.hunyuan.cloud.tencent.com/v1"
        if not config.default_model:
            config.default_model = "hunyuan-lite"
        super().__init__(config)
    
    def list_models(self) -> list[ModelInfo]:
        return self.MODELS

