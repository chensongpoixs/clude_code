"""
Google Cloud Vertex AI 提供商

文档: https://cloud.google.com/vertex-ai/docs
"""

from __future__ import annotations

import logging
import os
from typing import Any

from ..base import LLMProvider, ModelInfo, ProviderConfig
from ..registry import ProviderRegistry
from ..llama_cpp_http import ChatMessage

logger = logging.getLogger(__name__)


@ProviderRegistry.register("google_vertex")
class GoogleVertexProvider(LLMProvider):
    """
    Google Cloud Vertex AI 提供商。
    
    需要配置:
        - GOOGLE_CLOUD_PROJECT: GCP 项目 ID
        - GOOGLE_CLOUD_REGION: 区域 (如 us-central1)
        - GOOGLE_APPLICATION_CREDENTIALS: 服务账号 JSON 路径
    
    或使用 gcloud auth 认证。
    """
    
    PROVIDER_ID = "google_vertex"
    PROVIDER_NAME = "Google Vertex AI"
    PROVIDER_TYPE = "cloud"
    REGION = "海外"
    
    # 支持的模型
    MODELS = {
        "gemini-1.5-pro": ModelInfo(
            id="gemini-1.5-pro",
            name="Gemini 1.5 Pro",
            context_window=2097152,
            supports_vision=True,
            supports_function_call=True,
        ),
        "gemini-1.5-flash": ModelInfo(
            id="gemini-1.5-flash",
            name="Gemini 1.5 Flash",
            context_window=1048576,
            supports_vision=True,
            supports_function_call=True,
        ),
        "gemini-1.0-pro": ModelInfo(
            id="gemini-1.0-pro",
            name="Gemini 1.0 Pro",
            context_window=32760,
            supports_vision=False,
            supports_function_call=True,
        ),
        "text-bison": ModelInfo(
            id="text-bison",
            name="PaLM 2 Text Bison",
            context_window=8192,
        ),
        "chat-bison": ModelInfo(
            id="chat-bison",
            name="PaLM 2 Chat Bison",
            context_window=8192,
        ),
    }
    
    def __init__(self, config: ProviderConfig | None = None):
        super().__init__(config)
        self._project = os.getenv("GOOGLE_CLOUD_PROJECT", "")
        self._region = os.getenv("GOOGLE_CLOUD_REGION", "us-central1")
        self._model = config.default_model if config else "gemini-1.5-pro"
        self._client = None
    
    def _ensure_client(self) -> Any:
        """确保 Vertex AI 客户端已初始化"""
        if self._client is not None:
            return self._client
        
        try:
            from google.cloud import aiplatform
            aiplatform.init(project=self._project, location=self._region)
            self._client = aiplatform
            return self._client
        except ImportError:
            raise ImportError(
                "需要安装 google-cloud-aiplatform: pip install google-cloud-aiplatform"
            )
    
    def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> str:
        """调用 Vertex AI 生成"""
        model_id = model or self._model
        
        try:
            from vertexai.generative_models import GenerativeModel, Content, Part
            
            # 转换消息格式
            contents = []
            for msg in messages:
                if msg.role == "system":
                    # Vertex AI 不直接支持 system，放到第一条 user 前面
                    continue
                role = "user" if msg.role == "user" else "model"
                content = msg.content if isinstance(msg.content, str) else str(msg.content)
                contents.append(Content(role=role, parts=[Part.from_text(content)]))
            
            # 创建模型
            gen_model = GenerativeModel(model_id)
            
            # 生成
            response = gen_model.generate_content(
                contents,
                generation_config={
                    "temperature": temperature,
                    "max_output_tokens": max_tokens,
                },
            )
            
            return response.text
            
        except ImportError:
            raise ImportError(
                "需要安装 google-cloud-aiplatform: pip install google-cloud-aiplatform"
            )
        except Exception as e:
            logger.error(f"Vertex AI 请求失败: {e}")
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

