from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import httpx


# Role 说明：
# - llama.cpp 的 OpenAI-compatible 接口本身支持 system/user/assistant（部分模板还会支持 tool）
# - 本项目当前会在消息历史中写入 assistant（例如工具调用 JSON、规划输出）
# - 因此这里必须包含 assistant，否则类型标注会误导后续维护/静态检查
Role = Literal["system", "user", "assistant"]  # 未来可扩展 "tool"


@dataclass(frozen=True)
class ChatMessage:
    role: Role
    content: str


class LlamaCppHttpClient:
    """
    Minimal llama.cpp HTTP client.

    Supports:
    - OpenAI-compatible: POST {base_url}/v1/chat/completions
    - Legacy completion: POST {base_url}/completion
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
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_mode = api_mode
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout_s = timeout_s

    def chat(self, messages: list[ChatMessage]) -> str:
        if self.api_mode == "openai_compat":
            return self._chat_openai_compat(messages)
        return self._chat_completion(messages)

    def try_get_first_model_id(self) -> str | None:
        """
        Best-effort helper for llama.cpp OpenAI-compatible servers.

        Many servers validate the `model` field; if you pass an unknown model id,
        `/v1/chat/completions` can return 400.
        """
        url = f"{self.base_url}/v1/models"
        try:
            with httpx.Client(timeout=min(self.timeout_s, 10)) as client:
                r = client.get(url)
                r.raise_for_status()
                data = r.json()
        except Exception:
            return None

        # OpenAI style: {"data":[{"id":"..."}]}
        try:
            items = data.get("data") or []
            if items and isinstance(items, list) and isinstance(items[0], dict) and "id" in items[0]:
                return str(items[0]["id"])
        except Exception:
            return None
        return None

    def list_model_ids(self) -> list[str]:
        """
        List model ids from OpenAI-compatible endpoint: GET {base_url}/v1/models
        Returns [] if not supported/unavailable.
        """
        url = f"{self.base_url}/v1/models"
        try:
            with httpx.Client(timeout=min(self.timeout_s, 10)) as client:
                r = client.get(url)
                r.raise_for_status()
                data = r.json()
        except Exception:
            return []

        out: list[str] = []
        try:
            items = data.get("data") or []
            if isinstance(items, list):
                for it in items:
                    if isinstance(it, dict) and "id" in it:
                        out.append(str(it["id"]))
        except Exception:
            return []
        return out

    def _chat_openai_compat(self, messages: list[ChatMessage]) -> str:
        url = f"{self.base_url}/v1/chat/completions"
        model = self.model
        if not model:
            model = self.try_get_first_model_id() or "llama.cpp"
        payload: dict[str, Any] = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": False,
        }
        with httpx.Client(timeout=self.timeout_s) as client:
            r = client.post(url, json=payload)
            if r.status_code >= 400:
                # Surface response body — llama.cpp often explains which field is invalid.
                body = r.text
                raise RuntimeError(
                    "llama.cpp OpenAI-compatible request failed: "
                    f"status={r.status_code} url={url} body={body[:2000]}"
                )
            data = r.json()

        # OpenAI style
        try:
            return data["choices"][0]["message"]["content"]
        except Exception:
            # Some servers may return choices[].text
            try:
                return data["choices"][0]["text"]
            except Exception as e:
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


