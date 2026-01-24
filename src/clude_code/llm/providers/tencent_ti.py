"""
腾讯云 TI 平台提供商

文档: https://cloud.tencent.com/product/ti
腾讯云智能钛机器学习平台。
"""

from __future__ import annotations

import logging
import os
from typing import Any

from ..base import LLMProvider, ModelInfo, ProviderConfig
from ..registry import ProviderRegistry
from ..llama_cpp_http import ChatMessage

logger = logging.getLogger(__name__)


@ProviderRegistry.register("tencent_ti")
class TencentTIProvider(LLMProvider):
    """
    腾讯云 TI 平台提供商。
    
    用于调用部署在腾讯云 TI 平台上的模型服务。
    
    需要配置:
        - TENCENT_SECRET_ID: 腾讯云 SecretId
        - TENCENT_SECRET_KEY: 腾讯云 SecretKey
        - TI_ENDPOINT: TI 平台服务端点
    """
    
    PROVIDER_ID = "tencent_ti"
    PROVIDER_NAME = "腾讯云 TI 平台"
    PROVIDER_TYPE = "cloud"
    REGION = "国内"
    
    def __init__(self, config: ProviderConfig | None = None):
        super().__init__(config)
        self._secret_id = os.getenv("TENCENT_SECRET_ID", "")
        self._secret_key = os.getenv("TENCENT_SECRET_KEY", "")
        self._endpoint = os.getenv("TI_ENDPOINT", "")
        self._model = config.default_model if config else ""
    
    def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> str:
        """调用 TI 平台服务"""
        import requests
        if not self._endpoint:
            raise ValueError("未配置 TI 平台端点")
        
        # 构建 prompt
        prompt_parts = []
        for msg in messages:
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            if msg.role == "system":
                prompt_parts.append(f"<|system|>\n{content}")
            elif msg.role == "user":
                prompt_parts.append(f"<|user|>\n{content}")
            else:
                prompt_parts.append(f"<|assistant|>\n{content}")
        
        prompt_parts.append("<|assistant|>")
        prompt = "\n".join(prompt_parts)
        
        headers = {
            "Content-Type": "application/json",
        }
        
        payload = {
            "prompt": prompt,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        
        try:
            response = requests.post(
                self._endpoint,
                headers=headers,
                json=payload,
                timeout=120,
            )
            response.raise_for_status()
            
            result = response.json()
            
            # 解析响应
            if isinstance(result, dict):
                if "generated_text" in result:
                    return result["generated_text"]
                if "response" in result:
                    return result["response"]
            
            return str(result)
            
        except Exception as e:
            logger.error(f"TI 平台请求失败: {e}")
            raise
    
    def list_models(self) -> list[ModelInfo]:
        """列出可用模型"""
        if self._model:
            return [ModelInfo(
                id=self._model,
                name=f"TI: {self._model}",
                context_window=4096,
            )]
        return []
    
    def get_model_info(self, model_id: str) -> ModelInfo | None:
        """获取模型信息"""
        return ModelInfo(
            id=model_id,
            name=f"TI: {model_id}",
            context_window=4096,
        )
    
    def set_model(self, model_id: str) -> None:
        """设置当前模型"""
        self._model = model_id
    
    def get_model(self) -> str:
        """获取当前模型"""
        return self._model

