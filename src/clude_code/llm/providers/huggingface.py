"""
Hugging Face Inference API 提供商

文档: https://huggingface.co/docs/api-inference/
"""

from __future__ import annotations

import logging
import os
from typing import Any

from ..base import LLMProvider, ModelInfo, ProviderConfig
from ..registry import ProviderRegistry
from ..llama_cpp_http import ChatMessage

logger = logging.getLogger(__name__)


@ProviderRegistry.register("huggingface")
class HuggingFaceProvider(LLMProvider):
    """
    Hugging Face Inference API 提供商。
    
    需要配置:
        - HUGGINGFACE_API_KEY: Hugging Face API 令牌
    """
    
    PROVIDER_ID = "huggingface"
    PROVIDER_NAME = "Hugging Face"
    PROVIDER_TYPE = "cloud"
    REGION = "海外"
    BASE_URL = "https://api-inference.huggingface.co/models"
    
    # 支持的模型
    MODELS = {
        "meta-llama/Llama-2-70b-chat-hf": ModelInfo(
            id="meta-llama/Llama-2-70b-chat-hf",
            name="Llama 2 70B Chat",
            context_window=4096,
        ),
        "mistralai/Mistral-7B-Instruct-v0.2": ModelInfo(
            id="mistralai/Mistral-7B-Instruct-v0.2",
            name="Mistral 7B Instruct",
            context_window=32768,
        ),
        "google/gemma-7b-it": ModelInfo(
            id="google/gemma-7b-it",
            name="Gemma 7B",
            context_window=8192,
        ),
        "microsoft/phi-2": ModelInfo(
            id="microsoft/phi-2",
            name="Phi-2",
            context_window=2048,
        ),
        "HuggingFaceH4/zephyr-7b-beta": ModelInfo(
            id="HuggingFaceH4/zephyr-7b-beta",
            name="Zephyr 7B",
            context_window=8192,
        ),
        "sentence-transformers/all-MiniLM-L6-v2": ModelInfo(
            id="sentence-transformers/all-MiniLM-L6-v2",
            name="Sentence Transformers MiniLM",
            context_window=512,
        ),
    }
    
    def __init__(self, config: ProviderConfig | None = None):
        super().__init__(config)
        self._api_key = os.getenv("HUGGINGFACE_API_KEY", "")
        self._model = config.default_model if config else "mistralai/Mistral-7B-Instruct-v0.2"
    
    def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> str:
        """调用 Hugging Face Inference API"""
        import requests
        model_id = model or self._model
        
        # 构建 prompt（适用于 instruct 模型）
        prompt_parts = []
        for msg in messages:
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            if msg.role == "system":
                prompt_parts.append(f"<|system|>\n{content}</s>")
            elif msg.role == "user":
                prompt_parts.append(f"<|user|>\n{content}</s>")
            else:
                prompt_parts.append(f"<|assistant|>\n{content}</s>")
        
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
                "return_full_text": False,
            },
        }
        
        try:
            response = requests.post(
                f"{self.BASE_URL}/{model_id}",
                headers=headers,
                json=payload,
                timeout=120,
            )
            response.raise_for_status()
            
            result = response.json()
            
            # 解析响应
            if isinstance(result, list) and len(result) > 0:
                return result[0].get("generated_text", str(result))
            elif isinstance(result, dict):
                return result.get("generated_text", str(result))
            
            return str(result)
            
        except Exception as e:
            logger.error(f"Hugging Face 请求失败: {e}")
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

