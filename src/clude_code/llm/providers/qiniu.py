"""
七牛云 LLM 提供商

文档: https://developer.qiniu.com/
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Iterator

from ..base import LLMProvider, ModelInfo, ProviderConfig
from ..registry import ProviderRegistry
from ..http_client import ChatMessage

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
    # 默认 base_url：如果用户未配置，使用本地测试端点（避免调用真实七牛云）
    # 注意：需要包含 /v1 后缀，因为 OpenAI-compatible API 路径是 /v1/chat/completions
    DEFAULT_BASE_URL = "http://127.0.0.1:11434/v1"
    
    # 支持的模型
    MODELS = {
        "qiniu-llm-v1": ModelInfo(
            id="qiniu-llm-v1",
            name="七牛 LLM v1",
            provider="qiniu",
            context_window=8192,
        ),
    }
    
    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self._access_key = config.api_key or os.getenv("QINIU_ACCESS_KEY", "")
        # 兼容保留（暂未用于签名）
        self._secret_key = os.getenv("QINIU_SECRET_KEY", "")
        
        # 规范化 base_url：确保以 /v1 或其他版本号结尾（OpenAI-compatible API 标准）
        raw_url = (config.base_url or os.getenv("QINIU_LLM_ENDPOINT", self.DEFAULT_BASE_URL)).rstrip("/")
        # 如果 URL 不以 /v 开头的版本号结尾（如 /v1, /v2），自动添加 /v1
        if not re.search(r'/v\d+$', raw_url):
            raw_url = raw_url + "/v1"
        self._base_url = raw_url
        
        # 统一：以基类 current_model 作为唯一事实源
        if not (self.current_model or "").strip():
            self.current_model = config.default_model or "qiniu-llm-v1"
    
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
        import httpx
        model_id = model or self.current_model or "qiniu-llm-v1"

        # 转换消息格式（OpenAI 兼容，含多模态）
        from ..image_utils import convert_to_openai_vision_format

        openai_messages: list[dict[str, Any]] = []
        for msg in messages:
            openai_messages.append(
                {
                    "role": msg.role,
                    "content": convert_to_openai_vision_format(msg.content),
                }
            )

        headers: dict[str, str] = {"Content-Type": "application/json"}
        # 注意：此处鉴权仅作占位/兼容；真实 Qiniu LLM 鉴权可能需要 AK/SK 签名。
        if self._access_key:
            headers["Authorization"] = f"QBox {self._access_key}"

        payload = {
            "model": model_id,
            "messages": openai_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        
        try:
            with httpx.Client(timeout=120) as client:
                response = client.post(
                    f"{self._base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                if response.status_code >= 400:
                    body = response.text[:2000]
                    raise RuntimeError(f"七牛云请求失败: HTTP {response.status_code} body={body}")

                result = response.json()
            
            # OpenAI 兼容格式
            if "choices" in result:
                return result["choices"][0]["message"]["content"]
            
            return str(result)
            
        except Exception as e:
            logger.error(f"七牛云请求失败: {e}")
            raise

    async def chat_async(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> str:
        """
        异步聊天（兼容实现）。

        七牛云当前实现基于同步 HTTP 请求；这里使用线程池降级以满足接口契约。
        """
        import asyncio

        return await asyncio.to_thread(
            self.chat,
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

    def chat_stream(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> Iterator[str]:
        """
        流式聊天（降级实现）。

        七牛云若不支持服务端 SSE/stream，这里用“单段 yield”保证调用方可用。
        """
        yield self.chat(
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )
    
    def list_models(self) -> list[ModelInfo]:
        """
        列出可用模型。

        业界对齐：
        - OpenAI-compatible 后端通常提供 GET /models
        - 若不可用（鉴权/不支持/网络失败），回退到静态列表
        """
        import httpx

        headers: dict[str, str] = {}
        if self._access_key:
            headers["Authorization"] = f"QBox {self._access_key}"
        try:
            # 优化：5 秒超时（连接 2 秒），避免等太久
            with httpx.Client(timeout=httpx.Timeout(5.0, connect=2.0)) as client:
                r = client.get(f"{self._base_url}/models", headers=headers)
                if r.status_code < 400:
                    data = r.json() or {}
                    items = data.get("data") if isinstance(data, dict) else None
                    if isinstance(items, list):
                        out: list[ModelInfo] = []
                        for it in items:
                            if not isinstance(it, dict):
                                continue
                            mid = str(it.get("id", "")).strip()
                            if not mid:
                                continue
                            # 优化：添加 context_window 字段
                            out.append(ModelInfo(
                                id=mid,
                                name=mid,
                                provider="qiniu",
                                context_window=it.get("context_length", 4096),
                            ))
                        if out:
                            return out
        except Exception as e:
            # 优化：添加调试日志
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"qiniu: 无法从 API 获取模型列表 ({e})，回退到静态列表")

        return list(self.MODELS.values())
    
    def get_model_info(self, model_id: str) -> ModelInfo | None:
        """获取模型信息（兼容：优先静态表）"""
        return self.MODELS.get(model_id)

    # 兼容旧接口（若外部仍调用 set_model/get_model）
    def set_model(self, model_id: str) -> None:
        self.current_model = model_id

    def get_model(self) -> str:
        return self.current_model

