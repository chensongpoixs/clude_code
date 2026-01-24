from __future__ import annotations

"""
通用 HTTP 客户端（OpenAI-compatible）。

背景：
- 历史上该模块实现位于 `llama_cpp_http.py`
- 但其能力并非 “llama.cpp 专用”，而是可复用于多种 OpenAI-compatible 服务

迁移策略：
- 新代码应优先从 `clude_code.llm.http_client` 导入
- `clude_code.llm.llama_cpp_http` 作为兼容层继续保留（re-export）
"""

from dataclasses import dataclass
from typing import Any, Literal, Union

import httpx
import logging
import os

logger = logging.getLogger(__name__)


# Role 说明：
# - llama.cpp 的 OpenAI-compatible 接口本身支持 system/user/assistant（部分模板还会支持 tool）
# - 本项目当前会在消息历史中写入 assistant（例如工具调用 JSON、规划输出）
# - 因此这里必须包含 assistant，否则类型标注会误导后续维护/静态检查
Role = Literal["system", "user", "assistant"]  # 未来可扩展 "tool"

# 多模态内容类型（OpenAI Vision API 格式）
ContentPart = dict[str, Any]  # {"type": "text", "text": "..."} 或 {"type": "image_url", "image_url": {...}}
MultimodalContent = list[ContentPart]


@dataclass
class ChatMessage:
    """
    聊天消息（支持纯文本和多模态）。

    content 可以是：
    - str: 纯文本消息
    - list[dict]: 多模态消息（OpenAI Vision API 格式）
    """

    role: Role
    content: Union[str, MultimodalContent]

    def __hash__(self) -> int:
        # 为了兼容旧代码中可能的 hash 需求
        if isinstance(self.content, str):
            return hash((self.role, self.content))
        return hash((self.role, str(self.content)[:100]))


# 支持的 LLM Provider（供文档和类型提示）
LLMProvider = Literal["llama_cpp_http", "openai", "anthropic", "ollama", "azure_openai", "siliconflow"]


class LlamaCppHttpClient:
    """
    通用 OpenAI 兼容 HTTP 客户端（Universal OpenAI-Compatible HTTP Client）。

    支持（Supports）：
    - llama.cpp / Ollama / vLLM 等本地 LLM（Local LLM）
    - OpenAI API（需 api_key）
    - Azure OpenAI（需 api_key + 特殊 base_url）
    - Anthropic（需 api_key，通过 OpenAI 兼容层）
    - 其他 OpenAI 兼容 API（Other OpenAI-Compatible APIs）

    API 模式（API Modes）：
    - openai_compat: POST {base_url}/v1/chat/completions（推荐）
    - completion: POST {base_url}/completion（llama.cpp 原生）
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_mode: Literal["openai_compat", "completion"] = "openai_compat",
        model: str = "",
        temperature: float = 0.2,
        max_tokens: int = 1024,
        timeout_s: int = 120,
        api_key: str = "",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_mode = api_mode
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout_s = timeout_s
        # API Key 优先级：参数 > 环境变量（按 provider 检测）> 空
        # 支持的环境变量：OPENAI_API_KEY / SILICONFLOW_API_KEY / ANTHROPIC_API_KEY / AZURE_OPENAI_API_KEY
        self.api_key = api_key or self._detect_api_key_from_env(base_url)

        # 模型切换回调（用于通知监听者）
        self._on_model_changed: list[callable] = []

    # ============================================================
    # 动态模型切换 API
    # ============================================================

    def set_model(self, model: str) -> None:
        """
        动态切换模型。

        参数:
            model: 新的模型名称/ID
        """
        old_model = self.model
        self.model = model

        # 触发回调
        for callback in self._on_model_changed:
            try:
                callback(old_model, model)
            except Exception as e:
                logger.warning(f"模型切换回调执行失败: {e}")

    def get_model(self) -> str:
        """获取当前模型名称"""
        return self.model

    def on_model_changed(self, callback: callable) -> None:
        """
        注册模型变更回调。

        回调签名: callback(old_model: str, new_model: str) -> None
        """
        self._on_model_changed.append(callback)

    def _detect_api_key_from_env(self, base_url: str) -> str:
        """根据 base_url 自动检测对应的 API Key 环境变量。"""
        url_lower = base_url.lower()
        # 按 provider 优先级检测
        if "siliconflow" in url_lower:
            return os.environ.get("SILICONFLOW_API_KEY", "")
        if "anthropic" in url_lower:
            return os.environ.get("ANTHROPIC_API_KEY", "")
        if "azure" in url_lower:
            return os.environ.get("AZURE_OPENAI_API_KEY", "")
        # 默认使用 OPENAI_API_KEY（兼容大多数 OpenAI 兼容服务）
        return os.environ.get("OPENAI_API_KEY", "")

    def chat(self, messages: list[ChatMessage]) -> str:
        if self.api_mode == "openai_compat":
            return self._chat_openai_compat(messages)
        return self._chat_completion(messages)

    def try_get_first_model_id(self) -> str | None:
        """
        Best-effort helper for OpenAI-compatible servers.

        Many servers validate the `model` field; if you pass an unknown model id,
        `/v1/chat/completions` can return 400.
        """
        url = f"{self.base_url}/v1/models"
        headers = self._build_headers()
        try:
            with httpx.Client(timeout=min(self.timeout_s, 10)) as client:
                r = client.get(url, headers=headers)
                r.raise_for_status()
                data = r.json()
        except Exception as e:
            logger.warning(f"获取模型 ID 失败 (try_get_first_model_id): {e}")
            return None

        # OpenAI style: {"data":[{"id":"..."}]}
        try:
            items = data.get("data") or []
            if items and isinstance(items, list) and isinstance(items[0], dict) and "id" in items[0]:
                return str(items[0]["id"])
        except Exception as e:
            logger.warning(f"解析模型列表失败: {e}")
            return None
        return None

    def list_model_ids(self) -> list[str]:
        """
        获取可用模型列表（List Available Models）。

        从 OpenAI 兼容端点获取：GET {base_url}/v1/models
        支持：OpenAI、Azure OpenAI、llama.cpp、Ollama 等。
        返回空列表如果不支持或不可用。
        """
        url = f"{self.base_url}/v1/models"
        headers = self._build_headers()
        try:
            with httpx.Client(timeout=min(self.timeout_s, 10)) as client:
                r = client.get(url, headers=headers)
                r.raise_for_status()
                data = r.json()
        except Exception as e:
            logger.error(f"无法从 {url} 获取模型列表: {e}", exc_info=True)
            return []

        out: list[str] = []
        try:
            items = data.get("data") or []
            if isinstance(items, list):
                for it in items:
                    if isinstance(it, dict) and "id" in it:
                        out.append(str(it["id"]))
        except Exception as e:
            logger.error(f"解析模型列表异常: {e}", exc_info=True)
            return []
        return out

    def _build_headers(self) -> dict[str, str]:
        """构建 HTTP 请求头（包含 API Key 认证）。"""
        headers: dict[str, str] = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _chat_openai_compat(self, messages: list[ChatMessage]) -> str:
        url = f"{self.base_url}/v1/chat/completions"
        model = self.model
        if not model:
            model = self.try_get_first_model_id() or "llama.cpp"

        # 转换消息格式：Claude Vision → OpenAI Vision
        from .image_utils import convert_to_openai_vision_format

        converted_messages = []
        for m in messages:
            converted_content = convert_to_openai_vision_format(m.content)
            converted_messages.append({"role": m.role, "content": converted_content})

        payload: dict[str, Any] = {
            "model": model,
            "messages": converted_messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": False,
        }
        headers = self._build_headers()
        try:
            with httpx.Client(timeout=self.timeout_s) as client:
                r = client.post(url, json=payload, headers=headers)
                if r.status_code >= 400:
                    logger.warning(
                        "llama.cpp OpenAI-compatible request failed: "
                        f"status={r.status_code} url={url} payload={payload} body={r.text}"
                    )
                    # Surface response body — llama.cpp often explains which field is invalid.
                    body = r.text
                    raise RuntimeError(
                        "llama.cpp OpenAI-compatible request failed: "
                        f"status={r.status_code} url={url} body={body}"
                    )
                data = r.json()
        except httpx.TimeoutException as e:
            logger.warning(
                "llama.cpp OpenAI-compatible request timed out: "
                f"url={url} timeout_s={self.timeout_s} payload={payload} err={e}"
            )
            raise RuntimeError(
                "llama.cpp OpenAI-compatible request failed: "
                f"timeout url={url} (timeout_s={self.timeout_s})"
            ) from e
        except httpx.RequestError as e:
            # 业界常见：代理/证书/连接失败。这里把根因抛给上层用于友好提示。
            logger.warning(
                "llama.cpp OpenAI-compatible request error: "
                f"url={url} timeout_s={self.timeout_s} payload={payload} err={e}"
            )
            raise RuntimeError(
                "llama.cpp OpenAI-compatible request failed: "
                f"request_error url={url} err={type(e).__name__}: {e}"
            ) from e

        # OpenAI style
        try:
            return data["choices"][0]["message"]["content"]
        except Exception:
            # Some servers may return choices[].text
            try:
                return data["choices"][0]["text"]
            except Exception as e:
                logger.warning(f"无法解析 llama.cpp OpenAI-compatible 响应: {e} 数据: {data}", exc_info=True)
                raise RuntimeError(f"unexpected response format: {data}") from e

    def _chat_completion(self, messages: list[ChatMessage]) -> str:
        # Fallback mode: build a plain prompt. This is intentionally simple for MVP.
        prompt = ""
        for m in messages:
            prompt += f"{m.role.upper()}: {m.content}\n"
        prompt += "ASSISTANT: "

        url = f"{self.base_url}/completion"
        payload: dict[str, Any] = {
            "prompt": prompt,
            "temperature": self.temperature,
            "n_predict": self.max_tokens,
        }
        with httpx.Client(timeout=self.timeout_s) as client:
            r = client.post(url, json=payload)
            if r.status_code >= 400:
                raise RuntimeError(
                    "llama.cpp completion request failed: "
                    f"status={r.status_code} url={url} body={r.text[:2000]}"
                )
            data = r.json()
        # llama.cpp typically returns {"content": "..."} for /completion
        return data.get("content") or data.get("completion") or ""


