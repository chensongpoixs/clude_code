"""
Replicate 提供商

文档: https://replicate.com/docs
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

from ..base import LLMProvider, ModelInfo, ProviderConfig
from ..registry import ProviderRegistry
from ..http_client import ChatMessage

logger = logging.getLogger(__name__)


@ProviderRegistry.register("replicate")
class ReplicateProvider(LLMProvider):
    """
    Replicate 提供商。
    
    需要配置:
        - REPLICATE_API_TOKEN: Replicate API 令牌
    """
    
    PROVIDER_ID = "replicate"
    PROVIDER_NAME = "Replicate"
    PROVIDER_TYPE = "cloud"
    REGION = "海外"
    BASE_URL = "https://api.replicate.com/v1"
    
    # 支持的模型
    MODELS = {
        "meta/llama-2-70b-chat": ModelInfo(
            id="meta/llama-2-70b-chat",
            name="Llama 2 70B Chat",
            context_window=4096,
        ),
        "meta/meta-llama-3-70b-instruct": ModelInfo(
            id="meta/meta-llama-3-70b-instruct",
            name="Llama 3 70B Instruct",
            context_window=8000,
        ),
        "mistralai/mixtral-8x7b-instruct-v0.1": ModelInfo(
            id="mistralai/mixtral-8x7b-instruct-v0.1",
            name="Mixtral 8x7B",
            context_window=32768,
        ),
        "stability-ai/sdxl": ModelInfo(
            id="stability-ai/sdxl",
            name="SDXL",
            context_window=0,
            supports_vision=True,
        ),
    }
    
    def __init__(self, config: ProviderConfig | None = None):
        super().__init__(config)
        self._api_token = os.getenv("REPLICATE_API_TOKEN", "")
        self._model = config.default_model if config else "meta/meta-llama-3-70b-instruct"
    
    def _wait_for_prediction(self, prediction_url: str, headers: dict) -> dict:
        """等待预测完成"""
        import requests
        max_attempts = 60
        for _ in range(max_attempts):
            response = requests.get(prediction_url, headers=headers, timeout=30)
            response.raise_for_status()
            result = response.json()
            
            status = result.get("status")
            if status == "succeeded":
                return result
            elif status == "failed":
                raise Exception(f"预测失败: {result.get('error')}")
            elif status == "canceled":
                raise Exception("预测被取消")
            
            time.sleep(2)
        
        raise Exception("预测超时")
    
    def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> str:
        """调用 Replicate"""
        import requests
        model_id = model or self._model
        
        # 构建 prompt
        prompt_parts = []
        system_prompt = ""
        
        for msg in messages:
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            if msg.role == "system":
                system_prompt = content
            elif msg.role == "user":
                prompt_parts.append(f"User: {content}")
            else:
                prompt_parts.append(f"Assistant: {content}")
        
        prompt = "\n".join(prompt_parts) + "\nAssistant:"
        
        headers = {
            "Authorization": f"Token {self._api_token}",
            "Content-Type": "application/json",
        }
        
        # 创建预测
        payload = {
            "version": model_id,
            "input": {
                "prompt": prompt,
                "max_new_tokens": max_tokens,
                "temperature": temperature,
            },
        }
        
        if system_prompt:
            payload["input"]["system_prompt"] = system_prompt
        
        try:
            response = requests.post(
                f"{self.BASE_URL}/predictions",
                headers=headers,
                json=payload,
                timeout=30,
            )
            response.raise_for_status()
            
            result = response.json()
            
            # 等待完成
            prediction_url = result.get("urls", {}).get("get")
            if prediction_url:
                result = self._wait_for_prediction(prediction_url, headers)
            
            # 解析输出
            output = result.get("output", "")
            if isinstance(output, list):
                return "".join(output)
            return str(output)
            
        except Exception as e:
            logger.error(f"Replicate 请求失败: {e}")
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

