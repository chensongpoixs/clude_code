"""
智谱 AI 厂商（Zhipu AI Provider）

GLM 系列模型支持。
"""

from __future__ import annotations

from ..base import ModelInfo, ProviderConfig
from ..registry import ProviderRegistry
from .openai_compat import OpenAICompatProvider


@ProviderRegistry.register("zhipu")
class ZhipuProvider(OpenAICompatProvider):
    """
    智谱 AI 厂商
    
    支持模型：glm-4, glm-4-flash, glm-4v 等
    """
    
    PROVIDER_NAME = "智谱 AI (ChatGLM)"
    PROVIDER_ID = "zhipu"
    PROVIDER_TYPE = "cloud"
    REGION = "国内"
    
    MODELS = [
        ModelInfo(
            id="glm-4-plus",
            name="GLM-4 Plus",
            provider="zhipu",
            context_window=128000,
            max_output_tokens=4096,
            supports_function_call=True,
            pricing={"input": 0.00005, "output": 0.00005},
        ),
        ModelInfo(
            id="glm-4",
            name="GLM-4",
            provider="zhipu",
            context_window=128000,
            max_output_tokens=4096,
            supports_function_call=True,
            pricing={"input": 0.0001, "output": 0.0001},
        ),
        ModelInfo(
            id="glm-4-flash",
            name="GLM-4 Flash",
            provider="zhipu",
            context_window=128000,
            max_output_tokens=4096,
            supports_function_call=True,
            pricing={"input": 0.000001, "output": 0.000001},
        ),
        ModelInfo(
            id="glm-4v-plus",
            name="GLM-4V Plus",
            provider="zhipu",
            context_window=8192,
            max_output_tokens=1024,
            supports_vision=True,
            pricing={"input": 0.00001, "output": 0.00001},
        ),
        ModelInfo(
            id="glm-4-long",
            name="GLM-4 Long",
            provider="zhipu",
            context_window=1000000,
            max_output_tokens=4096,
            pricing={"input": 0.000001, "output": 0.000001},
        ),
    ]
    
    def __init__(self, config: ProviderConfig):
        if not config.base_url:
            config.base_url = "https://open.bigmodel.cn/api/paas/v4"
        if not config.default_model:
            config.default_model = "glm-4"
        super().__init__(config)
    
    def list_models(self) -> list[ModelInfo]:
        return self.MODELS

