"""
Together.ai 厂商（Together Provider）

Together.ai 开源模型托管平台支持。
"""

from __future__ import annotations

from ..base import ModelInfo, ProviderConfig
from ..registry import ProviderRegistry
from .openai_compat import OpenAICompatProvider


@ProviderRegistry.register("together")
class TogetherProvider(OpenAICompatProvider):
    """
    Together.ai 厂商
    
    支持大量开源模型托管
    """
    
    PROVIDER_NAME = "Together.ai"
    PROVIDER_ID = "together"
    PROVIDER_TYPE = "cloud"
    REGION = "海外"
    
    MODELS = [
        ModelInfo(
            id="meta-llama/Meta-Llama-3.1-405B-Instruct-Turbo",
            name="Llama 3.1 405B Turbo",
            provider="together",
            context_window=130815,
            max_output_tokens=4096,
            supports_function_call=True,
            pricing={"input": 0.005, "output": 0.015},
        ),
        ModelInfo(
            id="meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo",
            name="Llama 3.1 70B Turbo",
            provider="together",
            context_window=131072,
            max_output_tokens=4096,
            supports_function_call=True,
            pricing={"input": 0.00088, "output": 0.00088},
        ),
        ModelInfo(
            id="Qwen/Qwen2.5-72B-Instruct-Turbo",
            name="Qwen 2.5 72B Turbo",
            provider="together",
            context_window=32768,
            max_output_tokens=4096,
            pricing={"input": 0.0012, "output": 0.0012},
        ),
        ModelInfo(
            id="deepseek-ai/DeepSeek-V3",
            name="DeepSeek V3",
            provider="together",
            context_window=64000,
            max_output_tokens=8192,
            pricing={"input": 0.0014, "output": 0.0028},
        ),
        ModelInfo(
            id="deepseek-ai/DeepSeek-R1",
            name="DeepSeek R1",
            provider="together",
            context_window=64000,
            max_output_tokens=8192,
            pricing={"input": 0.003, "output": 0.007},
        ),
        ModelInfo(
            id="mistralai/Mixtral-8x22B-Instruct-v0.1",
            name="Mixtral 8x22B",
            provider="together",
            context_window=65536,
            max_output_tokens=4096,
            pricing={"input": 0.0012, "output": 0.0012},
        ),
    ]
    
    def __init__(self, config: ProviderConfig):
        if not config.base_url:
            config.base_url = "https://api.together.xyz/v1"
        if not config.default_model:
            config.default_model = "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo"
        super().__init__(config)
    
    def list_models(self) -> list[ModelInfo]:
        return self.MODELS

