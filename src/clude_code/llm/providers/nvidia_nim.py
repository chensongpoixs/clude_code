"""
NVIDIA NIM 提供商

文档: https://docs.nvidia.com/nim/
NIM (NVIDIA Inference Microservice) 提供 OpenAI 兼容 API。
"""

from __future__ import annotations

import logging
import os
from typing import Any

from ..base import LLMProvider, ModelInfo, ProviderConfig
from ..registry import ProviderRegistry
from ..http_client import ChatMessage

logger = logging.getLogger(__name__)


@ProviderRegistry.register("nvidia_nim")
class NvidiaNIMProvider(LLMProvider):
    """
    NVIDIA NIM 提供商。
    
    NIM 提供 OpenAI 兼容的 API 接口。
    
    需要配置:
        - NVIDIA_NIM_API_KEY: NIM API 密钥
        - NVIDIA_NIM_BASE_URL: NIM 服务地址 (默认 https://integrate.api.nvidia.com/v1)
    """
    
    PROVIDER_ID = "nvidia_nim"
    PROVIDER_NAME = "NVIDIA NIM"
    PROVIDER_TYPE = "cloud"
    REGION = "海外"
    DEFAULT_BASE_URL = "https://integrate.api.nvidia.com/v1"
    
    # 支持的模型
    MODELS = {
        "meta/llama-3.1-405b-instruct": ModelInfo(
            id="meta/llama-3.1-405b-instruct",
            name="Llama 3.1 405B Instruct",
            context_window=128000,
            supports_function_call=True,
        ),
        "meta/llama-3.1-70b-instruct": ModelInfo(
            id="meta/llama-3.1-70b-instruct",
            name="Llama 3.1 70B Instruct",
            context_window=128000,
            supports_function_call=True,
        ),
        "meta/llama-3.1-8b-instruct": ModelInfo(
            id="meta/llama-3.1-8b-instruct",
            name="Llama 3.1 8B Instruct",
            context_window=128000,
        ),
        "nvidia/nemotron-4-340b-instruct": ModelInfo(
            id="nvidia/nemotron-4-340b-instruct",
            name="Nemotron-4 340B",
            context_window=4096,
        ),
        "mistralai/mixtral-8x22b-instruct-v0.1": ModelInfo(
            id="mistralai/mixtral-8x22b-instruct-v0.1",
            name="Mixtral 8x22B",
            context_window=65536,
        ),
        "google/gemma-2-27b-it": ModelInfo(
            id="google/gemma-2-27b-it",
            name="Gemma 2 27B",
            context_window=8192,
        ),
    }
    
    def __init__(self, config: ProviderConfig | None = None):
        super().__init__(config)
        self._api_key = os.getenv("NVIDIA_NIM_API_KEY", "")
        self._base_url = os.getenv("NVIDIA_NIM_BASE_URL", self.DEFAULT_BASE_URL)
        self._model = config.default_model if config else "meta/llama-3.1-70b-instruct"
    
    def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> str:
        """调用 NIM API"""
        import requests
        model_id = model or self._model
        
        # 转换消息格式（OpenAI 兼容）
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
        
        try:
            response = requests.post(
                f"{self._base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=120,
            )
            response.raise_for_status()
            
            result = response.json()
            return result["choices"][0]["message"]["content"]
            
        except Exception as e:
            logger.error(f"NVIDIA NIM 请求失败: {e}")
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

