"""
阶跃星辰 (Stepfun) 提供商

文档: https://platform.stepfun.com/docs
"""

from __future__ import annotations

import logging
import os
from typing import Any

from ..base import LLMProvider, ModelInfo, ProviderConfig
from ..registry import ProviderRegistry
from ..http_client import ChatMessage

logger = logging.getLogger(__name__)


@ProviderRegistry.register("stepfun")
class StepfunProvider(LLMProvider):
    """
    阶跃星辰 (Stepfun) 提供商。
    
    需要配置:
        - STEPFUN_API_KEY: Stepfun API 密钥
    """
    
    PROVIDER_ID = "stepfun"
    PROVIDER_NAME = "阶跃星辰 (Stepfun)"
    PROVIDER_TYPE = "cloud"
    REGION = "国内"
    BASE_URL = "https://api.stepfun.com/v1"
    
    # 支持的模型
    MODELS = {
        "step-1-8k": ModelInfo(
            id="step-1-8k",
            name="Step-1 8K",
            context_window=8192,
        ),
        "step-1-32k": ModelInfo(
            id="step-1-32k",
            name="Step-1 32K",
            context_window=32768,
        ),
        "step-1-128k": ModelInfo(
            id="step-1-128k",
            name="Step-1 128K",
            context_window=128000,
        ),
        "step-1-256k": ModelInfo(
            id="step-1-256k",
            name="Step-1 256K",
            context_window=256000,
        ),
        "step-1v-8k": ModelInfo(
            id="step-1v-8k",
            name="Step-1V 8K (Vision)",
            context_window=8192,
            supports_vision=True,
        ),
        "step-2-16k": ModelInfo(
            id="step-2-16k",
            name="Step-2 16K",
            context_window=16384,
        ),
    }
    
    def __init__(self, config: ProviderConfig | None = None):
        super().__init__(config)
        self._api_key = os.getenv("STEPFUN_API_KEY", "")
        self._model = config.default_model if config else "step-1-32k"
    
    def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> str:
        """调用 Stepfun"""
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
            logger.error(f"Stepfun 请求失败: {e}")
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

