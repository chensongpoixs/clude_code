"""
硅基流动 厂商（SiliconFlow Provider）

硅基流动模型托管平台支持。
"""

from __future__ import annotations

from ..base import ModelInfo, ProviderConfig
from ..registry import ProviderRegistry
from .openai_compat import OpenAICompatProvider


@ProviderRegistry.register("siliconflow")
class SiliconFlowProvider(OpenAICompatProvider):
    """
    硅基流动 厂商
    
    支持多种开源模型托管：DeepSeek, Qwen, Yi, Llama 等
    """
    
    PROVIDER_NAME = "硅基流动 (SiliconFlow)"
    PROVIDER_ID = "siliconflow"
    PROVIDER_TYPE = "cloud"
    REGION = "国内"
    
    MODELS = [
        # DeepSeek 系列
        ModelInfo(
            id="deepseek-ai/DeepSeek-V3",
            name="DeepSeek V3",
            provider="siliconflow",
            context_window=64000,
            max_output_tokens=8192,
            supports_function_call=True,
        ),
        ModelInfo(
            id="deepseek-ai/DeepSeek-R1",
            name="DeepSeek R1",
            provider="siliconflow",
            context_window=64000,
            max_output_tokens=8192,
        ),
        ModelInfo(
            id="deepseek-ai/DeepSeek-R1-Distill-Qwen-32B",
            name="DeepSeek R1 Distill Qwen 32B",
            provider="siliconflow",
            context_window=32768,
            max_output_tokens=8192,
        ),
        # Qwen 系列
        ModelInfo(
            id="Qwen/Qwen2.5-72B-Instruct",
            name="Qwen 2.5 72B",
            provider="siliconflow",
            context_window=131072,
            max_output_tokens=8192,
            supports_function_call=True,
        ),
        ModelInfo(
            id="Qwen/Qwen2.5-32B-Instruct",
            name="Qwen 2.5 32B",
            provider="siliconflow",
            context_window=131072,
            max_output_tokens=8192,
            supports_function_call=True,
        ),
        ModelInfo(
            id="Qwen/Qwen2.5-Coder-32B-Instruct",
            name="Qwen 2.5 Coder 32B",
            provider="siliconflow",
            context_window=32768,
            max_output_tokens=8192,
        ),
        ModelInfo(
            id="Qwen/QwQ-32B-Preview",
            name="QwQ 32B Preview",
            provider="siliconflow",
            context_window=32768,
            max_output_tokens=8192,
        ),
        # 其他模型
        ModelInfo(
            id="meta-llama/Llama-3.3-70B-Instruct",
            name="Llama 3.3 70B",
            provider="siliconflow",
            context_window=131072,
            max_output_tokens=8192,
            supports_function_call=True,
        ),
        ModelInfo(
            id="01-ai/Yi-1.5-34B-Chat-16K",
            name="Yi 1.5 34B",
            provider="siliconflow",
            context_window=16384,
            max_output_tokens=4096,
        ),
    ]
    
    def __init__(self, config: ProviderConfig):
        if not config.base_url:
            config.base_url = "https://api.siliconflow.cn/v1"
        if not config.default_model:
            config.default_model = "deepseek-ai/DeepSeek-V3"
        super().__init__(config)
    
    def list_models(self) -> list[ModelInfo]:
        return self.MODELS

