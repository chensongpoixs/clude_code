"""
PerfXCloud 提供商

文档: https://perfxcloud.com/
OpenAI 兼容的推理平台。
"""

from __future__ import annotations

import logging
import os
from typing import Any

from ..base import LLMProvider, ModelInfo, ProviderConfig
from ..registry import ProviderRegistry
from ..llama_cpp_http import ChatMessage

logger = logging.getLogger(__name__)


@ProviderRegistry.register("perfxcloud")
class PerfXCloudProvider(LLMProvider):
    """
    PerfXCloud 提供商。
    
    提供 OpenAI 兼容 API。
    
    需要配置:
        - PERFXCLOUD_API_KEY: API 密钥
        - PERFXCLOUD_BASE_URL: 服务地址 (可选)
    """
    
    PROVIDER_ID = "perfxcloud"
    PROVIDER_NAME = "PerfXCloud"
    PROVIDER_TYPE = "cloud"
    REGION = "国内"
    DEFAULT_BASE_URL = "https://api.perfxcloud.com/v1"
    
    # 支持的模型
    MODELS = {
        "llama-3.1-70b": ModelInfo(
            id="llama-3.1-70b",
            name="Llama 3.1 70B",
            context_window=128000,
        ),
        "llama-3.1-8b": ModelInfo(
            id="llama-3.1-8b",
            name="Llama 3.1 8B",
            context_window=128000,
        ),
        "mixtral-8x7b": ModelInfo(
            id="mixtral-8x7b",
            name="Mixtral 8x7B",
            context_window=32768,
        ),
    }
    
    def __init__(self, config: ProviderConfig | None = None):
        super().__init__(config)
        self._api_key = os.getenv("PERFXCLOUD_API_KEY", "")
        self._base_url = os.getenv("PERFXCLOUD_BASE_URL", self.DEFAULT_BASE_URL)
        self._model = config.default_model if config else "llama-3.1-70b"
    
    def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> str:
        """调用 PerfXCloud"""
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
            logger.error(f"PerfXCloud 请求失败: {e}")
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

