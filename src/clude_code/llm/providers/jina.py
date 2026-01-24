"""
Jina AI 提供商

文档: https://jina.ai/embeddings/
专注于 Embedding 和 Rerank 能力。
"""

from __future__ import annotations

import logging
import os
from typing import Any

from ..base import LLMProvider, ModelInfo, ProviderConfig
from ..registry import ProviderRegistry
from ..llama_cpp_http import ChatMessage

logger = logging.getLogger(__name__)


@ProviderRegistry.register("jina")
class JinaProvider(LLMProvider):
    """
    Jina AI 提供商。
    
    专注于 Embedding 和 Rerank，也支持 Reader 和 Search。
    
    需要配置:
        - JINA_API_KEY: Jina API 密钥
    """
    
    PROVIDER_ID = "jina"
    PROVIDER_NAME = "Jina AI"
    PROVIDER_TYPE = "cloud"
    REGION = "海外"
    BASE_URL = "https://api.jina.ai/v1"
    
    # 支持的模型
    MODELS = {
        "jina-embeddings-v3": ModelInfo(
            id="jina-embeddings-v3",
            name="Jina Embeddings v3",
            context_window=8192,
        ),
        "jina-embeddings-v2-base-en": ModelInfo(
            id="jina-embeddings-v2-base-en",
            name="Jina Embeddings v2 Base EN",
            context_window=8192,
        ),
        "jina-reranker-v2-base-multilingual": ModelInfo(
            id="jina-reranker-v2-base-multilingual",
            name="Jina Reranker v2",
            context_window=1024,
        ),
        "jina-colbert-v2": ModelInfo(
            id="jina-colbert-v2",
            name="Jina ColBERT v2",
            context_window=8192,
        ),
    }
    
    def __init__(self, config: ProviderConfig | None = None):
        super().__init__(config)
        self._api_key = os.getenv("JINA_API_KEY", "")
        self._model = config.default_model if config else "jina-embeddings-v3"
    
    def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> str:
        """
        Jina 主要用于 Embedding/Rerank，不直接支持 chat。
        这里使用 Jina Reader API 作为替代。
        """
        import requests
        model_id = model or self._model
        
        # 提取最后一条用户消息
        user_content = ""
        for msg in reversed(messages):
            if msg.role == "user":
                user_content = msg.content if isinstance(msg.content, str) else str(msg.content)
                break
        
        if not user_content:
            return "请提供查询内容"
        
        # 使用 Jina Reader API 进行内容提取
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        
        # 如果是 URL，使用 Reader API
        if user_content.startswith("http"):
            try:
                response = requests.get(
                    f"https://r.jina.ai/{user_content}",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    timeout=30,
                )
                response.raise_for_status()
                return response.text
            except Exception as e:
                logger.error(f"Jina Reader 请求失败: {e}")
                raise
        
        # 否则返回提示
        return f"Jina AI 主要提供 Embedding 和 Rerank 服务。当前模型: {model_id}"
    
    def embed(self, texts: list[str], model: str | None = None) -> list[list[float]]:
        """生成嵌入向量"""
        import requests
        model_id = model or "jina-embeddings-v3"
        
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        
        payload = {
            "model": model_id,
            "input": texts,
        }
        
        try:
            response = requests.post(
                f"{self.BASE_URL}/embeddings",
                headers=headers,
                json=payload,
                timeout=60,
            )
            response.raise_for_status()
            
            result = response.json()
            return [item["embedding"] for item in result.get("data", [])]
            
        except Exception as e:
            logger.error(f"Jina Embedding 请求失败: {e}")
            raise
    
    def rerank(
        self,
        query: str,
        documents: list[str],
        model: str | None = None,
        top_n: int = 10,
    ) -> list[dict]:
        """重排序文档"""
        import requests
        model_id = model or "jina-reranker-v2-base-multilingual"
        
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        
        payload = {
            "model": model_id,
            "query": query,
            "documents": documents,
            "top_n": top_n,
        }
        
        try:
            response = requests.post(
                f"{self.BASE_URL}/rerank",
                headers=headers,
                json=payload,
                timeout=60,
            )
            response.raise_for_status()
            
            result = response.json()
            return result.get("results", [])
            
        except Exception as e:
            logger.error(f"Jina Rerank 请求失败: {e}")
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

