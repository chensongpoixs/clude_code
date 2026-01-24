"""
魔搭社区 (ModelScope) 提供商

文档: https://modelscope.cn/docs
"""

from __future__ import annotations

import logging
import os
from typing import Any

from ..base import LLMProvider, ModelInfo, ProviderConfig
from ..registry import ProviderRegistry
from ..http_client import ChatMessage

logger = logging.getLogger(__name__)


@ProviderRegistry.register("modelscope")
class ModelScopeProvider(LLMProvider):
    """
    魔搭社区 (ModelScope) 提供商。
    
    需要配置:
        - MODELSCOPE_API_KEY: ModelScope API 密钥
    """
    
    PROVIDER_ID = "modelscope"
    PROVIDER_NAME = "魔搭社区 (ModelScope)"
    PROVIDER_TYPE = "cloud"
    REGION = "国内"
    BASE_URL = "https://api-inference.modelscope.cn/api-inference/v1/models"
    
    # 支持的模型
    MODELS = {
        "qwen/Qwen2.5-72B-Instruct": ModelInfo(
            id="qwen/Qwen2.5-72B-Instruct",
            name="Qwen 2.5 72B Instruct",
            context_window=32768,
        ),
        "qwen/Qwen2.5-32B-Instruct": ModelInfo(
            id="qwen/Qwen2.5-32B-Instruct",
            name="Qwen 2.5 32B Instruct",
            context_window=32768,
        ),
        "qwen/Qwen2.5-7B-Instruct": ModelInfo(
            id="qwen/Qwen2.5-7B-Instruct",
            name="Qwen 2.5 7B Instruct",
            context_window=32768,
        ),
        "deepseek-ai/DeepSeek-V2.5": ModelInfo(
            id="deepseek-ai/DeepSeek-V2.5",
            name="DeepSeek V2.5",
            context_window=65536,
        ),
        "THUDM/chatglm3-6b": ModelInfo(
            id="THUDM/chatglm3-6b",
            name="ChatGLM3 6B",
            context_window=8192,
        ),
    }
    
    def __init__(self, config: ProviderConfig | None = None):
        super().__init__(config)
        self._api_key = os.getenv("MODELSCOPE_API_KEY", "")
        self._model = config.default_model if config else "qwen/Qwen2.5-72B-Instruct"
    
    def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> str:
        """调用 ModelScope"""
        import requests
        model_id = model or self._model
        
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
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        
        payload = {
            "inputs": prompt,
            "parameters": {
                "max_new_tokens": max_tokens,
                "temperature": temperature,
                "do_sample": temperature > 0,
            },
        }
        
        try:
            response = requests.post(
                f"{self.BASE_URL}/{model_id}/text-generation",
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
                if "Data" in result and "generated_text" in result["Data"]:
                    return result["Data"]["generated_text"]
            
            return str(result)
            
        except Exception as e:
            logger.error(f"ModelScope 请求失败: {e}")
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

