"""
Lepton AI 提供商

文档: https://www.lepton.ai/docs
"""

from __future__ import annotations

import logging
import os
from typing import Any

from ..base import LLMProvider, ModelInfo, ProviderConfig
from ..registry import ProviderRegistry
from ..http_client import ChatMessage

logger = logging.getLogger(__name__)


@ProviderRegistry.register("lepton")
class LeptonProvider(LLMProvider):
    """
    Lepton AI 提供商。
    
    提供 OpenAI 兼容 API。
    
    需要配置:
        - LEPTON_API_KEY: Lepton API 密钥
        - LEPTON_WORKSPACE: Lepton 工作空间 (可选)
    """
    
    PROVIDER_ID = "lepton"
    PROVIDER_NAME = "Lepton AI"
    PROVIDER_TYPE = "cloud"
    REGION = "海外"
    DEFAULT_BASE_URL = "https://llama3-70b.lepton.run/api/v1"
    
    # 支持的模型
    MODELS = {
        "llama3-70b": ModelInfo(
            id="llama3-70b",
            name="Llama 3 70B",
            context_window=8000,
        ),
        "llama3-8b": ModelInfo(
            id="llama3-8b",
            name="Llama 3 8B",
            context_window=8000,
        ),
        "mixtral-8x7b": ModelInfo(
            id="mixtral-8x7b",
            name="Mixtral 8x7B",
            context_window=32768,
        ),
        "codellama-34b": ModelInfo(
            id="codellama-34b",
            name="Code Llama 34B",
            context_window=16384,
        ),
    }
    
    def __init__(self, config: ProviderConfig | None = None):
        super().__init__(config)
        self._api_key = os.getenv("LEPTON_API_KEY", "")
        self._workspace = os.getenv("LEPTON_WORKSPACE", "")
        self._model = config.default_model if config else "llama3-70b"
        self._base_url = self._get_base_url(self._model)
    
    def _get_base_url(self, model: str) -> str:
        """获取模型对应的 API 端点"""
        # Lepton 每个模型有独立的端点
        model_endpoints = {
            "llama3-70b": "https://llama3-70b.lepton.run/api/v1",
            "llama3-8b": "https://llama3-8b.lepton.run/api/v1",
            "mixtral-8x7b": "https://mixtral-8x7b.lepton.run/api/v1",
            "codellama-34b": "https://codellama-34b.lepton.run/api/v1",
        }
        return model_endpoints.get(model, self.DEFAULT_BASE_URL)
    
    def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> str:
        """调用 Lepton AI"""
        import requests
        model_id = model or self._model
        base_url = self._get_base_url(model_id)
        
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
                f"{base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=120,
            )
            response.raise_for_status()
            
            result = response.json()
            return result["choices"][0]["message"]["content"]
            
        except Exception as e:
            logger.error(f"Lepton AI 请求失败: {e}")
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
        self._base_url = self._get_base_url(model_id)
    
    def get_model(self) -> str:
        """获取当前模型"""
        return self._model

