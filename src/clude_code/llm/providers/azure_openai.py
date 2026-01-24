"""
Azure OpenAI 厂商（Azure OpenAI Provider）

Azure OpenAI 服务支持。
"""

from __future__ import annotations

import logging
from typing import Any, Iterator, TYPE_CHECKING

import httpx

from ..base import ModelInfo, ProviderConfig
from ..registry import ProviderRegistry
from .openai_compat import OpenAICompatProvider

if TYPE_CHECKING:
    from ..llama_cpp_http import ChatMessage

logger = logging.getLogger(__name__)


@ProviderRegistry.register("azure_openai")
class AzureOpenAIProvider(OpenAICompatProvider):
    """
    Azure OpenAI 厂商
    
    特点：
    - 使用部署名而非模型名
    - 需要 api-version 参数
    - 端点格式不同
    """
    
    PROVIDER_NAME = "Azure OpenAI"
    PROVIDER_ID = "azure_openai"
    PROVIDER_TYPE = "cloud"
    REGION = "海外/合规"
    
    MODELS = [
        ModelInfo(
            id="gpt-4o",
            name="GPT-4o (Azure)",
            provider="azure_openai",
            context_window=128000,
            max_output_tokens=16384,
            supports_vision=True,
            supports_function_call=True,
        ),
        ModelInfo(
            id="gpt-4o-mini",
            name="GPT-4o Mini (Azure)",
            provider="azure_openai",
            context_window=128000,
            max_output_tokens=16384,
            supports_vision=True,
            supports_function_call=True,
        ),
        ModelInfo(
            id="gpt-4-turbo",
            name="GPT-4 Turbo (Azure)",
            provider="azure_openai",
            context_window=128000,
            max_output_tokens=4096,
            supports_vision=True,
            supports_function_call=True,
        ),
        ModelInfo(
            id="gpt-35-turbo",
            name="GPT-3.5 Turbo (Azure)",
            provider="azure_openai",
            context_window=16385,
            max_output_tokens=4096,
            supports_function_call=True,
        ),
    ]
    
    def __init__(self, config: ProviderConfig):
        if not config.api_version:
            config.api_version = "2024-02-15-preview"
        if not config.default_model:
            config.default_model = "gpt-4o"
        super().__init__(config)
        
        # Azure 使用不同的认证头
        self._client = httpx.Client(
            base_url=self.base_url,
            headers={
                "api-key": self.api_key,
                "Content-Type": "application/json",
            },
            timeout=self.timeout,
        )
    
    def _get_endpoint(self, deployment: str) -> str:
        """获取 Azure 端点"""
        api_version = self.config.api_version or "2024-02-15-preview"
        return f"/openai/deployments/{deployment}/chat/completions?api-version={api_version}"
    
    def chat(
        self,
        messages: list["ChatMessage"],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> str:
        """Azure OpenAI 聊天"""
        deployment = model or self.current_model or self.config.default_model
        
        # 检查是否有部署映射
        deployment_map = self.config.extra.get("deployment_map", {})
        deployment = deployment_map.get(deployment, deployment)
        
        payload = {
            "messages": self._build_messages(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        payload.update(kwargs)
        
        try:
            resp = self._client.post(self._get_endpoint(deployment), json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except httpx.HTTPStatusError as e:
            logger.error(f"Azure OpenAI API 请求失败: {e.response.status_code} - {e.response.text}")
            raise
    
    def list_models(self) -> list[ModelInfo]:
        return self.MODELS

