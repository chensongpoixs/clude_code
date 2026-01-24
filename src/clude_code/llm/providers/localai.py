"""
LocalAI 提供商

文档: https://localai.io/
OpenAI 兼容的本地 LLM 推理。
"""

from __future__ import annotations

import logging
import os
from typing import Any

from ..base import LLMProvider, ModelInfo, ProviderConfig
from ..registry import ProviderRegistry
from ..llama_cpp_http import ChatMessage

logger = logging.getLogger(__name__)


@ProviderRegistry.register("localai")
class LocalAIProvider(LLMProvider):
    """
    LocalAI 提供商。
    
    提供 OpenAI 兼容 API。
    
    需要配置:
        - LOCALAI_BASE_URL: LocalAI 服务地址 (如 http://localhost:8080)
        - LOCALAI_API_KEY: API 密钥 (可选)
    """
    
    PROVIDER_ID = "localai"
    PROVIDER_NAME = "LocalAI"
    PROVIDER_TYPE = "local"
    REGION = "通用"
    DEFAULT_BASE_URL = "http://localhost:8080/v1"
    
    def __init__(self, config: ProviderConfig | None = None):
        super().__init__(config)
        self._base_url = os.getenv("LOCALAI_BASE_URL", self.DEFAULT_BASE_URL)
        self._api_key = os.getenv("LOCALAI_API_KEY", "")
        self._model = config.default_model if config else ""
        self._models_cache: list[ModelInfo] = []
    
    def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> str:
        """调用 LocalAI"""
        import requests
        model_id = model or self._model
        
        if not model_id:
            models = self.list_models()
            if models:
                model_id = models[0].id
            else:
                raise ValueError("未配置模型且无法获取可用模型列表")
        
        # 转换消息格式（OpenAI 兼容）
        openai_messages = []
        for msg in messages:
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            openai_messages.append({
                "role": msg.role,
                "content": content,
            })
        
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        
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
            logger.error(f"LocalAI 请求失败: {e}")
            raise
    
    def list_models(self) -> list[ModelInfo]:
        """列出可用模型"""
        import requests
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        
        try:
            response = requests.get(
                f"{self._base_url}/models",
                headers=headers,
                timeout=10,
            )
            response.raise_for_status()
            
            result = response.json()
            models = []
            
            for model in result.get("data", []):
                models.append(ModelInfo(
                    id=model.get("id", ""),
                    name=model.get("id", ""),
                    context_window=4096,  # LocalAI 默认
                ))
            
            self._models_cache = models
            return models
            
        except Exception as e:
            logger.warning(f"无法从 LocalAI 获取模型列表: {e}")
            return self._models_cache
    
    def get_model_info(self, model_id: str) -> ModelInfo | None:
        """获取模型信息"""
        models = self.list_models()
        for m in models:
            if m.id == model_id:
                return m
        return None
    
    def set_model(self, model_id: str) -> None:
        """设置当前模型"""
        self._model = model_id
    
    def get_model(self) -> str:
        """获取当前模型"""
        return self._model

