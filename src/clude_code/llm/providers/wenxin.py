"""
文心一言 厂商（Wenxin/ERNIE Provider）

百度文心一言系列模型支持。
"""

from __future__ import annotations

from ..base import ModelInfo, ProviderConfig
from ..registry import ProviderRegistry
from .openai_compat import OpenAICompatProvider


@ProviderRegistry.register("wenxin")
class WenxinProvider(OpenAICompatProvider):
    """
    文心一言 厂商
    
    支持模型：ernie-4.0, ernie-3.5 等
    """
    
    PROVIDER_NAME = "文心一言 (Wenxin)"
    PROVIDER_ID = "wenxin"
    PROVIDER_TYPE = "cloud"
    REGION = "国内"
    
    MODELS = [
        ModelInfo(
            id="ernie-4.0-8k",
            name="ERNIE 4.0 8K",
            provider="wenxin",
            context_window=8192,
            max_output_tokens=4096,
            supports_function_call=True,
            pricing={"input": 0.00012, "output": 0.00012},
        ),
        ModelInfo(
            id="ernie-4.0-turbo-8k",
            name="ERNIE 4.0 Turbo 8K",
            provider="wenxin",
            context_window=8192,
            max_output_tokens=4096,
            pricing={"input": 0.00003, "output": 0.00006},
        ),
        ModelInfo(
            id="ernie-3.5-8k",
            name="ERNIE 3.5 8K",
            provider="wenxin",
            context_window=8192,
            max_output_tokens=4096,
            pricing={"input": 0.000012, "output": 0.000012},
        ),
        ModelInfo(
            id="ernie-3.5-128k",
            name="ERNIE 3.5 128K",
            provider="wenxin",
            context_window=131072,
            max_output_tokens=4096,
            pricing={"input": 0.000024, "output": 0.000024},
        ),
        ModelInfo(
            id="ernie-speed-8k",
            name="ERNIE Speed 8K",
            provider="wenxin",
            context_window=8192,
            max_output_tokens=4096,
            pricing={"input": 0.0, "output": 0.0},  # 免费
        ),
        ModelInfo(
            id="ernie-lite-8k",
            name="ERNIE Lite 8K",
            provider="wenxin",
            context_window=8192,
            max_output_tokens=4096,
            pricing={"input": 0.0, "output": 0.0},  # 免费
        ),
    ]
    
    def __init__(self, config: ProviderConfig):
        if not config.base_url:
            config.base_url = "https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat"
        if not config.default_model:
            config.default_model = "ernie-3.5-8k"
        super().__init__(config)
    
    def list_models(self) -> list[ModelInfo]:
        return self.MODELS

