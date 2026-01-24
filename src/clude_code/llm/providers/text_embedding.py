"""
Text Embedding Inference (TEI) 提供商

文档: https://github.com/huggingface/text-embeddings-inference
Hugging Face 的专用嵌入推理服务。
"""

from __future__ import annotations

import logging
import os
from typing import Any

from ..base import LLMProvider, ModelInfo, ProviderConfig
from ..registry import ProviderRegistry
from ..http_client import ChatMessage

logger = logging.getLogger(__name__)


@ProviderRegistry.register("text_embedding")
class TextEmbeddingProvider(LLMProvider):
    """
    Text Embedding Inference 提供商。
    
    专注于高效的文本嵌入生成。
    
    需要配置:
        - TEI_BASE_URL: TEI 服务地址 (如 http://localhost:8080)
        - TEI_MODEL: 模型名称 (可选)
    """
    
    PROVIDER_ID = "text_embedding"
    PROVIDER_NAME = "Text Embedding (TEI)"
    PROVIDER_TYPE = "local"
    REGION = "通用"
    DEFAULT_BASE_URL = "http://localhost:8080"
    
    # 支持的模型
    MODELS = {
        "bge-large-en-v1.5": ModelInfo(
            id="bge-large-en-v1.5",
            name="BGE Large EN v1.5",
            context_window=512,
        ),
        "bge-base-en-v1.5": ModelInfo(
            id="bge-base-en-v1.5",
            name="BGE Base EN v1.5",
            context_window=512,
        ),
        "e5-large-v2": ModelInfo(
            id="e5-large-v2",
            name="E5 Large v2",
            context_window=512,
        ),
        "multilingual-e5-large": ModelInfo(
            id="multilingual-e5-large",
            name="Multilingual E5 Large",
            context_window=512,
        ),
    }
    
    def __init__(self, config: ProviderConfig | None = None):
        super().__init__(config)
        self._base_url = os.getenv("TEI_BASE_URL", self.DEFAULT_BASE_URL)
        self._model = os.getenv("TEI_MODEL", "") or (config.default_model if config else "bge-large-en-v1.5")
    
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
        TEI 主要用于嵌入，不直接支持 chat。
        返回嵌入信息作为响应。
        """
        import requests
        # 提取最后一条用户消息
        user_content = ""
        for msg in reversed(messages):
            if msg.role == "user":
                user_content = msg.content if isinstance(msg.content, str) else str(msg.content)
                break
        
        if not user_content:
            return "请提供要嵌入的文本"
        
        # 生成嵌入
        embeddings = self.embed([user_content])
        if embeddings:
            return f"已生成嵌入向量，维度: {len(embeddings[0])}"
        return "嵌入生成失败"
    
    def embed(self, texts: list[str]) -> list[list[float]]:
        """生成嵌入向量"""
        import requests
        try:
            response = requests.post(
                f"{self._base_url}/embed",
                json={"inputs": texts},
                timeout=60,
            )
            response.raise_for_status()
            
            result = response.json()
            
            # TEI 返回格式
            if isinstance(result, list):
                return result
            
            return []
            
        except Exception as e:
            logger.error(f"TEI 嵌入请求失败: {e}")
            raise
    
    def rerank(
        self,
        query: str,
        documents: list[str],
        top_n: int = 10,
    ) -> list[dict]:
        """重排序文档（如果 TEI 支持）"""
        import requests
        try:
            response = requests.post(
                f"{self._base_url}/rerank",
                json={
                    "query": query,
                    "texts": documents,
                    "truncate": True,
                },
                timeout=60,
            )
            response.raise_for_status()
            
            result = response.json()
            return result[:top_n] if isinstance(result, list) else []
            
        except Exception as e:
            logger.warning(f"TEI 重排序不可用: {e}")
            return []
    
    def list_models(self) -> list[ModelInfo]:
        """列出可用模型"""
        import requests
        # 尝试从 TEI 获取模型信息
        try:
            response = requests.get(
                f"{self._base_url}/info",
                timeout=10,
            )
            response.raise_for_status()
            
            info = response.json()
            model_id = info.get("model_id", self._model)
            
            return [ModelInfo(
                id=model_id,
                name=model_id,
                context_window=info.get("max_input_length", 512),
            )]
            
        except Exception:
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

