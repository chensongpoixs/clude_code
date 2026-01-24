"""
通用 OpenAI 兼容厂商（OpenAI Compatible Provider）

支持任何兼容 OpenAI API 的服务：
- llama.cpp
- Ollama
- vLLM
- LocalAI
- 自定义 API
"""

from __future__ import annotations

import json
import logging
from typing import Any, Iterator, TYPE_CHECKING

import httpx

from ..base import LLMProvider, ModelInfo, ProviderConfig
from ..registry import ProviderRegistry

if TYPE_CHECKING:
    from ..llama_cpp_http import ChatMessage

logger = logging.getLogger(__name__)


@ProviderRegistry.register("openai_compat")
class OpenAICompatProvider(LLMProvider):
    """
    通用 OpenAI 兼容厂商
    
    特点：
    - 兼容任何实现 OpenAI API 的服务
    - 支持动态模型列表查询
    - 支持流式输出
    """
    
    PROVIDER_NAME = "OpenAI Compatible"
    PROVIDER_ID = "openai_compat"
    PROVIDER_TYPE = "local"
    REGION = "通用"
    
    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        
        self.base_url = config.base_url.rstrip("/") if config.base_url else "http://127.0.0.1:8899"
        self.api_key = config.api_key or "no-key"
        self.timeout = config.timeout_s
        
        # HTTP 客户端
        self._client = httpx.Client(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=self.timeout,
        )
        
        # 模型缓存
        self._models_cache: list[ModelInfo] | None = None
    
    def _build_messages(self, messages: list["ChatMessage"]) -> list[dict]:
        """将 ChatMessage 转换为 OpenAI 格式"""
        result = []
        for msg in messages:
            if isinstance(msg.content, str):
                result.append({"role": msg.role, "content": msg.content})
            else:
                # 多模态内容
                result.append({"role": msg.role, "content": msg.content})
        return result
    
    def chat(
        self,
        messages: list["ChatMessage"],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> str:
        """同步聊天"""
        model = model or self.current_model or self.config.default_model
        
        payload = {
            "model": model,
            "messages": self._build_messages(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        payload.update(kwargs)
        
        try:
            resp = self._client.post("/v1/chat/completions", json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except httpx.HTTPStatusError as e:
            logger.error(f"OpenAI 兼容 API 请求失败: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"OpenAI 兼容 API 请求异常: {e}")
            raise
    
    async def chat_async(
        self,
        messages: list["ChatMessage"],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> str:
        """异步聊天"""
        model = model or self.current_model or self.config.default_model
        
        payload = {
            "model": model,
            "messages": self._build_messages(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        payload.update(kwargs)
        
        async with httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=self.timeout,
        ) as client:
            resp = await client.post("/v1/chat/completions", json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
    
    def chat_stream(
        self,
        messages: list["ChatMessage"],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> Iterator[str]:
        """流式聊天"""
        model = model or self.current_model or self.config.default_model
        
        payload = {
            "model": model,
            "messages": self._build_messages(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        payload.update(kwargs)
        
        with self._client.stream("POST", "/v1/chat/completions", json=payload) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                data_str = line[6:]  # 去掉 "data: " 前缀
                if data_str == "[DONE]":
                    break
                try:
                    data = json.loads(data_str)
                    delta = data.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        yield content
                except json.JSONDecodeError:
                    continue
    
    def list_models(self) -> list[ModelInfo]:
        """获取可用模型列表"""
        if self._models_cache is not None:
            return self._models_cache
        
        try:
            resp = self._client.get("/v1/models")
            resp.raise_for_status()
            data = resp.json()
            
            models = []
            for item in data.get("data", []):
                model_id = item.get("id", "")
                models.append(ModelInfo(
                    id=model_id,
                    name=model_id,
                    provider=self.PROVIDER_ID,
                    context_window=item.get("context_window", 4096),
                    max_output_tokens=item.get("max_output_tokens", 4096),
                    supports_vision=item.get("supports_vision", False),
                    supports_function_call=item.get("supports_function_call", False),
                    supports_streaming=True,
                ))
            
            self._models_cache = models
            return models
        except Exception as e:
            logger.warning(f"获取模型列表失败: {e}")
            # 返回默认模型
            return [ModelInfo(
                id=self.config.default_model or "default",
                name=self.config.default_model or "Default Model",
                provider=self.PROVIDER_ID,
            )]
    
    def validate_config(self) -> tuple[bool, str]:
        """验证配置"""
        if not self.base_url:
            return False, "base_url 不能为空"
        return True, "配置有效"
    
    def test_connection(self) -> tuple[bool, str]:
        """测试连接"""
        try:
            resp = self._client.get("/v1/models")
            if resp.status_code == 200:
                data = resp.json()
                count = len(data.get("data", []))
                return True, f"连接成功，可用模型: {count} 个"
            return False, f"连接失败: HTTP {resp.status_code}"
        except httpx.ConnectError:
            return False, f"无法连接到 {self.base_url}"
        except Exception as e:
            return False, f"连接异常: {e}"

