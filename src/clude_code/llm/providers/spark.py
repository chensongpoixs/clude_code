"""
讯飞星火 厂商（Spark Provider）

讯飞星火系列模型支持。
"""

from __future__ import annotations

from ..base import ModelInfo, ProviderConfig
from ..registry import ProviderRegistry
from .openai_compat import OpenAICompatProvider


@ProviderRegistry.register("spark")
class SparkProvider(OpenAICompatProvider):
    """
    讯飞星火 厂商
    
    支持模型：spark-lite, spark-pro, spark-max 等
    """
    
    PROVIDER_NAME = "讯飞星火 (Spark)"
    PROVIDER_ID = "spark"
    PROVIDER_TYPE = "cloud"
    REGION = "国内"
    
    MODELS = [
        ModelInfo(
            id="4.0Ultra",
            name="Spark 4.0 Ultra",
            provider="spark",
            context_window=128000,
            max_output_tokens=8192,
            supports_function_call=True,
            pricing={"input": 0.00014, "output": 0.00014},
        ),
        ModelInfo(
            id="max-32k",
            name="Spark Max 32K",
            provider="spark",
            context_window=32768,
            max_output_tokens=8192,
            pricing={"input": 0.00003, "output": 0.00003},
        ),
        ModelInfo(
            id="generalv3.5",
            name="Spark Pro",
            provider="spark",
            context_window=8192,
            max_output_tokens=4096,
            pricing={"input": 0.000003, "output": 0.000003},
        ),
        ModelInfo(
            id="lite",
            name="Spark Lite",
            provider="spark",
            context_window=4096,
            max_output_tokens=4096,
            pricing={"input": 0.0, "output": 0.0},  # 免费
        ),
    ]
    
    def __init__(self, config: ProviderConfig):
        if not config.base_url:
            config.base_url = "https://spark-api-open.xf-yun.com/v1"
        if not config.default_model:
            config.default_model = "generalv3.5"
        super().__init__(config)
    
    def list_models(self) -> list[ModelInfo]:
        return self.MODELS

