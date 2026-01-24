"""
GPUStack 提供商

文档: https://gpustack.ai/
OpenAI 兼容的本地 GPU 推理平台。
"""

from __future__ import annotations

import logging
import os
from typing import Any

from ..base import LLMProvider, ModelInfo, ProviderConfig
from ..registry import ProviderRegistry
from ..http_client import ChatMessage

logger = logging.getLogger(__name__)


@ProviderRegistry.register("gpustack")
class GPUStackProvider(LLMProvider):
    """
    GPUStack 提供商。
    
    提供 OpenAI 兼容 API。
    
    需要配置:
        - GPUSTACK_BASE_URL: GPUStack 服务地址 (如 http://localhost:8080)
        - GPUSTACK_API_KEY: API 密钥 (可选)
    """
    
    PROVIDER_ID = "gpustack"
    PROVIDER_NAME = "GPUStack"
    PROVIDER_TYPE = "local"
    REGION = "通用"
    DEFAULT_BASE_URL = "http://localhost:8080/v1"
    
    def __init__(self, config: ProviderConfig | None = None):
        super().__init__(config)
        self._base_url = os.getenv("GPUSTACK_BASE_URL", self.DEFAULT_BASE_URL)
        self._api_key = os.getenv("GPUSTACK_API_KEY", "")
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
        """调用 GPUStack"""
        import requests
        model_id = model or self._model
        
        if not model_id:
            # 尝试获取第一个可用模型
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
            logger.error(f"GPUStack 请求失败: {e}")
            raise
    
    def list_models(self) -> list[ModelInfo]:
        """列出可用模型（从 GPUStack 获取）"""
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
                    id=model.get("id", model.get("name", "")),
                    name=model.get("name", model.get("id", "")),
                    context_window=model.get("context_length", 4096),
                ))
            
            self._models_cache = models
            return models
            
        except Exception as e:
            logger.warning(f"无法从 GPUStack 获取模型列表: {e}")
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

