"""
七牛云 LLM 提供商

文档: https://developer.qiniu.com/
"""

from __future__ import annotations

import logging
import os
from typing import Any

from ..base import LLMProvider, ModelInfo, ProviderConfig
from ..registry import ProviderRegistry
from ..llama_cpp_http import ChatMessage

logger = logging.getLogger(__name__)


@ProviderRegistry.register("qiniu")
class QiniuProvider(LLMProvider):
    """
    七牛云 LLM 提供商。
    
    需要配置:
        - QINIU_ACCESS_KEY: 七牛云 AccessKey
        - QINIU_SECRET_KEY: 七牛云 SecretKey
        - QINIU_LLM_ENDPOINT: LLM 服务端点 (可选)
    """
    
    PROVIDER_ID = "qiniu"
    PROVIDER_NAME = "七牛云 LLM"
    PROVIDER_TYPE = "cloud"
    REGION = "国内"
    DEFAULT_BASE_URL = "https://llm.qiniuapi.com/v1"
    
    # 支持的模型
    MODELS = {
        "qiniu-llm-v1": ModelInfo(
            id="qiniu-llm-v1",
            name="七牛 LLM v1",
            context_window=8192,
        ),
    }
    
    def __init__(self, config: ProviderConfig | None = None):
        super().__init__(config)
        self._access_key = os.getenv("QINIU_ACCESS_KEY", "")
        self._secret_key = os.getenv("QINIU_SECRET_KEY", "")
        self._base_url = os.getenv("QINIU_LLM_ENDPOINT", self.DEFAULT_BASE_URL)
        self._model = config.default_model if config else "qiniu-llm-v1"
    
    def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> str:
        """调用七牛云 LLM"""
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
            "Authorization": f"QBox {self._access_key}",
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
            
            # OpenAI 兼容格式
            if "choices" in result:
                return result["choices"][0]["message"]["content"]
            
            return str(result)
            
        except Exception as e:
            logger.error(f"七牛云请求失败: {e}")
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

