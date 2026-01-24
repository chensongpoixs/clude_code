"""
NVIDIA API Catalog 提供商

文档: https://build.nvidia.com/
NVIDIA AI Foundation Models 和 NGC Catalog。
"""

from __future__ import annotations

import logging
import os
from typing import Any

from ..base import LLMProvider, ModelInfo, ProviderConfig
from ..registry import ProviderRegistry
from ..http_client import ChatMessage

logger = logging.getLogger(__name__)


@ProviderRegistry.register("nvidia_catalog")
class NvidiaCatalogProvider(LLMProvider):
    """
    NVIDIA API Catalog 提供商。
    
    提供对 NVIDIA AI Foundation Models 的访问。
    
    需要配置:
        - NVIDIA_API_KEY: NVIDIA API 密钥
    """
    
    PROVIDER_ID = "nvidia_catalog"
    PROVIDER_NAME = "NVIDIA API Catalog"
    PROVIDER_TYPE = "cloud"
    REGION = "海外"
    BASE_URL = "https://api.nvcf.nvidia.com/v2/nvcf"
    
    # 支持的模型
    MODELS = {
        "nvidia/llama-3.1-nemotron-70b-instruct": ModelInfo(
            id="nvidia/llama-3.1-nemotron-70b-instruct",
            name="Llama 3.1 Nemotron 70B",
            context_window=32768,
            supports_function_call=True,
        ),
        "nvidia/nemotron-mini-4b-instruct": ModelInfo(
            id="nvidia/nemotron-mini-4b-instruct",
            name="Nemotron Mini 4B",
            context_window=4096,
        ),
        "nvidia/nv-embedqa-e5-v5": ModelInfo(
            id="nvidia/nv-embedqa-e5-v5",
            name="NV-EmbedQA E5 v5",
            context_window=512,
        ),
        "nvidia/nv-rerankqa-mistral-4b-v3": ModelInfo(
            id="nvidia/nv-rerankqa-mistral-4b-v3",
            name="NV-RerankQA Mistral 4B",
            context_window=4096,
        ),
    }
    
    def __init__(self, config: ProviderConfig | None = None):
        super().__init__(config)
        self._api_key = os.getenv("NVIDIA_API_KEY", "")
        self._model = config.default_model if config else "nvidia/llama-3.1-nemotron-70b-instruct"
    
    def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> str:
        """调用 NVIDIA API Catalog"""
        import requests
        model_id = model or self._model
        
        # 转换消息格式
        openai_messages = []
        for msg in messages:
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            openai_messages.append({
                "role": msg.role,
                "content": content,
            })
        
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        
        payload = {
            "model": model_id,
            "messages": openai_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        
        # 使用 OpenAI 兼容端点
        try:
            response = requests.post(
                "https://integrate.api.nvidia.com/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=120,
            )
            response.raise_for_status()
            
            result = response.json()
            return result["choices"][0]["message"]["content"]
            
        except Exception as e:
            logger.error(f"NVIDIA API Catalog 请求失败: {e}")
            raise
    
    def list_models(self) -> list[ModelInfo]:
        """列出可用模型"""
        return list(self.MODELS.values())
    
    def get_model_info(self, model_id: str) -> ModelInfo | None:
        """获取模型信息"""
        return self.MODELS.get(model_id)
    
    def set_model(self, model_id: str) -> None:
        """设置当前模型"""
        self._model = model_id
    
    def get_model(self) -> str:
        """获取当前模型"""
        return self._model

