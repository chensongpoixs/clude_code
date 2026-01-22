from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import httpx
import logging
import os
import random
import time

logger = logging.getLogger(__name__)


# Role 说明：
# - llama.cpp 的 OpenAI-compatible 接口本身支持 system/user/assistant（部分模板还会支持 tool）
# - 本项目当前会在消息历史中写入 assistant（例如工具调用 JSON、规划输出）
# - 因此这里必须包含 assistant，否则类型标注会误导后续维护/静态检查
Role = Literal["system", "user", "assistant"]  # 未来可扩展 "tool"


@dataclass(frozen=True)
class ChatMessage:
    role: Role
    content: str


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
        model = self.model or (self.try_get_first_model_id() or "llama.cpp")
        base_payload: dict[str, Any] = {
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": False,
        }
        headers = self._build_headers()

        # 降级策略：指数退避重试（超时/网络错误/429/5xx）
        max_attempts = 3
        last_err: str = ""
        last_status: int | None = None
        for attempt in range(max_attempts):
            payload = {**base_payload, "model": model}
            try:
                with httpx.Client(timeout=self.timeout_s) as client:
                    r = client.post(url, json=payload, headers=headers)
                last_status = r.status_code

                # transient retry
                if r.status_code in (429, 502, 503, 504) and attempt < max_attempts - 1:
                    backoff = 0.5 * (2 ** attempt) + random.uniform(0, 0.2)
                    time.sleep(backoff)
                    continue

                if r.status_code >= 400:
                    body = r.text
                    # 典型：模型 id 不被识别 → 允许自动切换一次模型（只在显式 model 失败时）
                    if r.status_code == 400 and self.model and attempt == 0:
                        auto = self.try_get_first_model_id()
                        if auto and auto != model:
                            logger.warning(f"model rejected by server, fallback to first model id: {auto}")
                            model = auto
                            continue
                    raise RuntimeError(
                        "llama.cpp OpenAI-compatible request failed: "
                        f"status={r.status_code} url={url} body={body}"
                    )

                data = r.json()
                # OpenAI style
                try:
                    return data["choices"][0]["message"]["content"]
                except Exception:
                    try:
                        return data["choices"][0]["text"]
                    except Exception as e:
                        raise RuntimeError(f"unexpected response format: {data}") from e

            except httpx.TimeoutException as e:
                last_err = f"timeout url={url} (timeout_s={self.timeout_s})"
                if attempt < max_attempts - 1:
                    backoff = 0.5 * (2 ** attempt) + random.uniform(0, 0.2)
                    time.sleep(backoff)
                    continue
                raise RuntimeError(
                    "llama.cpp OpenAI-compatible request failed: "
                    f"{last_err}"
                ) from e
            except httpx.RequestError as e:
                last_err = f"request_error url={url} err={type(e).__name__}: {e}"
                if attempt < max_attempts - 1:
                    backoff = 0.5 * (2 ** attempt) + random.uniform(0, 0.2)
                    time.sleep(backoff)
                    continue
                raise RuntimeError(
                    "llama.cpp OpenAI-compatible request failed: "
                    f"{last_err}"
                ) from e
            except Exception as e:
                # 非 httpx 异常：不做重试（避免重复触发非幂等错误）
                raise

        raise RuntimeError(f"llama.cpp OpenAI-compatible request failed: status={last_status} err={last_err}")

        # OpenAI style
        try:
            return data["choices"][0]["message"]["content"]
        except Exception:
            # Some servers may return choices[].text
            try:
                return data["choices"][0]["text"]
            except Exception as e:
                logger.warning(f"无法解析 llama.cpp OpenAI-compatible 响应: {e} 数据: {data}", exc_info=True);
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
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                with httpx.Client(timeout=self.timeout_s) as client:
                    r = client.post(url, json=payload)
                if r.status_code in (429, 502, 503, 504) and attempt < max_attempts - 1:
                    backoff = 0.5 * (2 ** attempt) + random.uniform(0, 0.2)
                    time.sleep(backoff)
                    continue
                if r.status_code >= 400:
                    raise RuntimeError(
                        "llama.cpp completion request failed: "
                        f"status={r.status_code} url={url} body={r.text[:2000]}"
                    )
                data = r.json()
                break
            except httpx.TimeoutException as e:
                if attempt < max_attempts - 1:
                    backoff = 0.5 * (2 ** attempt) + random.uniform(0, 0.2)
                    time.sleep(backoff)
                    continue
                raise RuntimeError(
                    "llama.cpp completion request failed: "
                    f"timeout url={url} (timeout_s={self.timeout_s})"
                ) from e
            except httpx.RequestError as e:
                if attempt < max_attempts - 1:
                    backoff = 0.5 * (2 ** attempt) + random.uniform(0, 0.2)
                    time.sleep(backoff)
                    continue
                raise RuntimeError(
                    "llama.cpp completion request failed: "
                    f"request_error url={url} err={type(e).__name__}: {e}"
                ) from e
        # llama.cpp typically returns {"content": "..."} for /completion
        return data.get("content") or data.get("completion") or ""


