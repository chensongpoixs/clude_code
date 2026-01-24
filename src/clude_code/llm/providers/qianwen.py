"""
通义千问 厂商（Qianwen/Tongyi Provider）

阿里云通义千问系列模型支持。
"""

from __future__ import annotations

from ..base import ModelInfo, ProviderConfig
from ..registry import ProviderRegistry
from .openai_compat import OpenAICompatProvider


@ProviderRegistry.register("qianwen")
class QianwenProvider(OpenAICompatProvider):
    """
    通义千问 厂商
    
    支持模型：qwen-turbo, qwen-plus, qwen-max 等
    """
    
    PROVIDER_NAME = "通义千问 (Tongyi)"
    PROVIDER_ID = "qianwen"
    PROVIDER_TYPE = "cloud"
    REGION = "国内"
    
    MODELS = [
        ModelInfo(
            id="qwen-max",
            name="Qwen Max",
            provider="qianwen",
            context_window=32768,
            max_output_tokens=8192,
            supports_function_call=True,
            pricing={"input": 0.00002, "output": 0.00006},
        ),
        ModelInfo(
            id="qwen-max-longcontext",
            name="Qwen Max Long",
            provider="qianwen",
            context_window=30720,
            max_output_tokens=8192,
            pricing={"input": 0.00002, "output": 0.00006},
        ),
        ModelInfo(
            id="qwen-plus",
            name="Qwen Plus",
            provider="qianwen",
            context_window=131072,
            max_output_tokens=8192,
            supports_function_call=True,
            pricing={"input": 0.000004, "output": 0.000012},
        ),
        ModelInfo(
            id="qwen-turbo",
            name="Qwen Turbo",
            provider="qianwen",
            context_window=131072,
            max_output_tokens=8192,
            supports_function_call=True,
            pricing={"input": 0.000002, "output": 0.000006},
        ),
        ModelInfo(
            id="qwen-vl-max",
            name="Qwen VL Max",
            provider="qianwen",
            context_window=32768,
            max_output_tokens=2048,
            supports_vision=True,
            pricing={"input": 0.00002, "output": 0.00006},
        ),
        ModelInfo(
            id="qwen-vl-plus",
            name="Qwen VL Plus",
            provider="qianwen",
            context_window=8192,
            max_output_tokens=2048,
            supports_vision=True,
            pricing={"input": 0.000008, "output": 0.000008},
        ),
    ]
    
    def __init__(self, config: ProviderConfig):
        if not config.base_url:
            config.base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
        if not config.default_model:
            config.default_model = "qwen-turbo"
        super().__init__(config)
    
    def list_models(self) -> list[ModelInfo]:
        return self.MODELS

