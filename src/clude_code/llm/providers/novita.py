"""
novita.ai 提供商

文档: https://novita.ai/docs
"""

from __future__ import annotations

import logging
import os
from typing import Any

from ..base import LLMProvider, ModelInfo, ProviderConfig
from ..registry import ProviderRegistry
from ..http_client import ChatMessage

logger = logging.getLogger(__name__)


@ProviderRegistry.register("novita")
class NovitaProvider(LLMProvider):
    """
    novita.ai 提供商。
    
    提供 OpenAI 兼容 API。
    
    需要配置:
        - NOVITA_API_KEY: novita API 密钥
    """
    
    PROVIDER_ID = "novita"
    PROVIDER_NAME = "novita.ai"
    PROVIDER_TYPE = "cloud"
    REGION = "海外"
    BASE_URL = "https://api.novita.ai/v3/openai"
    
    # 支持的模型
    MODELS = {
        "meta-llama/llama-3.1-70b-instruct": ModelInfo(
            id="meta-llama/llama-3.1-70b-instruct",
            name="Llama 3.1 70B Instruct",
            context_window=128000,
        ),
        "meta-llama/llama-3.1-8b-instruct": ModelInfo(
            id="meta-llama/llama-3.1-8b-instruct",
            name="Llama 3.1 8B Instruct",
            context_window=128000,
        ),
        "mistralai/mistral-nemo-instruct": ModelInfo(
            id="mistralai/mistral-nemo-instruct",
            name="Mistral Nemo",
            context_window=128000,
        ),
        "qwen/qwen-2.5-72b-instruct": ModelInfo(
            id="qwen/qwen-2.5-72b-instruct",
            name="Qwen 2.5 72B",
            context_window=32768,
        ),
    }
    
    def __init__(self, config: ProviderConfig | None = None):
        super().__init__(config)
        self._api_key = os.getenv("NOVITA_API_KEY", "")
        self._model = config.default_model if config else "meta-llama/llama-3.1-70b-instruct"
    
    def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> str:
        """调用 novita.ai"""
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
                f"{self.BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
                timeout=120,
            )
            response.raise_for_status()
            
            result = response.json()
            return result["choices"][0]["message"]["content"]
            
        except Exception as e:
            logger.error(f"novita.ai 请求失败: {e}")
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

