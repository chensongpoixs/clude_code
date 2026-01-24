"""
llama.cpp 提供商（llama.cpp Provider）

本地 LLM 推理服务器，支持：
- OpenAI 兼容 API（推荐）
- 原生 /completion API
- 服务器健康检查
- 槽位状态监控
- 多模态（llava）

文档: https://github.com/ggerganov/llama.cpp/blob/master/examples/server/README.md
"""

from __future__ import annotations

import logging
import os
from typing import Any, Iterator, TYPE_CHECKING

import httpx

from ..base import LLMProvider, ModelInfo, ProviderConfig
from ..registry import ProviderRegistry

if TYPE_CHECKING:
    from ..llama_cpp_http import ChatMessage

logger = logging.getLogger(__name__)


@ProviderRegistry.register("llama_cpp")
class LlamaCppProvider(LLMProvider):
    """
    llama.cpp 本地推理提供商。
    
    特点：
    - 本地运行，无需 API Key
    - 支持 GGUF 格式模型
    - 低延迟、高隐私
    - 支持 GPU 加速（CUDA/Metal/Vulkan）
    
    配置示例：
        providers:
          llama_cpp:
            base_url: "http://127.0.0.1:8899"
            default_model: "auto"
            extra:
              n_ctx: 32768
              repeat_penalty: 1.1
    """
    
    PROVIDER_ID = "llama_cpp"
    PROVIDER_NAME = "llama.cpp (本地)"
    PROVIDER_TYPE = "local"
    REGION = "通用"
    
    # 默认参数
    DEFAULT_BASE_URL = "http://127.0.0.1:8899"
    DEFAULT_N_CTX = 32768
    DEFAULT_N_PREDICT = 4096
    DEFAULT_REPEAT_PENALTY = 1.1
    DEFAULT_TIMEOUT = 120
    
    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        
        # 基础配置
        self.base_url = (config.base_url or os.environ.get("LLAMA_CPP_BASE_URL") or self.DEFAULT_BASE_URL).rstrip("/")
        self.api_key = config.api_key or os.environ.get("LLAMA_CPP_API_KEY") or ""
        self.timeout = config.timeout_s or self.DEFAULT_TIMEOUT
        
        # llama.cpp 特有参数
        extra = config.extra or {}
        self.n_ctx = extra.get("n_ctx", self.DEFAULT_N_CTX)
        self.n_predict = extra.get("n_predict", self.DEFAULT_N_PREDICT)
        self.repeat_penalty = extra.get("repeat_penalty", self.DEFAULT_REPEAT_PENALTY)
        self.n_gpu_layers = extra.get("n_gpu_layers", -1)  # -1 表示全部加载到 GPU
        
        # API 模式
        self.api_mode = extra.get("api_mode", "openai_compat")  # openai_compat 或 completion
        
        # HTTP 客户端
        self._client: httpx.Client | None = None
        
        # 模型缓存
        self._models_cache: list[ModelInfo] | None = None
        self._server_info_cache: dict | None = None
    
    def _get_client(self) -> httpx.Client:
        """获取或创建 HTTP 客户端"""
        if self._client is None:
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            
            self._client = httpx.Client(
                base_url=self.base_url,
                headers=headers,
                timeout=self.timeout,
            )
        return self._client
    
    def _build_messages(self, messages: list["ChatMessage"]) -> list[dict]:
        """将 ChatMessage 转换为 OpenAI 格式"""
        from ..image_utils import convert_to_openai_vision_format
        
        result = []
        for msg in messages:
            converted_content = convert_to_openai_vision_format(msg.content)
            result.append({"role": msg.role, "content": converted_content})
        return result
    
    def chat(
        self,
        messages: list["ChatMessage"],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> str:
        """
        调用 llama.cpp 进行聊天。
        
        支持两种模式：
        - openai_compat: 使用 /v1/chat/completions（推荐）
        - completion: 使用 /completion（原生模式）
        """
        if self.api_mode == "completion":
            return self._chat_completion(messages, temperature=temperature, max_tokens=max_tokens, **kwargs)
        return self._chat_openai_compat(messages, model=model, temperature=temperature, max_tokens=max_tokens, **kwargs)
    
    def _chat_openai_compat(
        self,
        messages: list["ChatMessage"],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> str:
        """使用 OpenAI 兼容 API"""
        client = self._get_client()
        
        # 自动检测模型
        model_id = model or self._model
        if not model_id or model_id == "auto":
            model_id = self._auto_detect_model()
        
        payload = {
            "model": model_id,
            "messages": self._build_messages(messages),
            "temperature": temperature,
            "max_tokens": max_tokens or self.n_predict,
            "stream": False,
        }
        
        # 添加 llama.cpp 特有参数
        if self.repeat_penalty != 1.0:
            payload["repeat_penalty"] = self.repeat_penalty
        
        payload.update(kwargs)
        
        try:
            resp = client.post("/v1/chat/completions", json=payload)
            
            if resp.status_code >= 400:
                error_body = resp.text[:500]
                logger.error(f"llama.cpp API 错误: status={resp.status_code} body={error_body}")
                raise RuntimeError(f"llama.cpp 请求失败: HTTP {resp.status_code} - {error_body}")
            
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        
        except httpx.TimeoutException:
            logger.error(f"llama.cpp 请求超时: url={self.base_url} timeout={self.timeout}s")
            raise RuntimeError(f"llama.cpp 请求超时（{self.timeout}s），请检查服务器状态或增加超时时间")
        
        except httpx.ConnectError:
            logger.error(f"无法连接到 llama.cpp 服务器: {self.base_url}")
            raise RuntimeError(f"无法连接到 llama.cpp 服务器 {self.base_url}，请确保服务已启动")
        
        except Exception as e:
            logger.error(f"llama.cpp 请求异常: {e}")
            raise
    
    def _chat_completion(
        self,
        messages: list["ChatMessage"],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> str:
        """使用原生 /completion API"""
        client = self._get_client()
        
        # 构建 prompt
        prompt = ""
        for m in messages:
            content = m.content if isinstance(m.content, str) else str(m.content)
            prompt += f"{m.role.upper()}: {content}\n"
        prompt += "ASSISTANT: "
        
        payload = {
            "prompt": prompt,
            "temperature": temperature,
            "n_predict": max_tokens or self.n_predict,
            "repeat_penalty": self.repeat_penalty,
        }
        payload.update(kwargs)
        
        try:
            resp = client.post("/completion", json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data.get("content") or data.get("completion") or ""
        except Exception as e:
            logger.error(f"llama.cpp /completion 请求失败: {e}")
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
        model_id = model or self._model
        if not model_id or model_id == "auto":
            model_id = self._auto_detect_model()
        
        payload = {
            "model": model_id,
            "messages": self._build_messages(messages),
            "temperature": temperature,
            "max_tokens": max_tokens or self.n_predict,
            "stream": False,
        }
        if self.repeat_penalty != 1.0:
            payload["repeat_penalty"] = self.repeat_penalty
        payload.update(kwargs)
        
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        
        async with httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers,
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
        import json as json_lib
        
        client = self._get_client()
        model_id = model or self._model
        if not model_id or model_id == "auto":
            model_id = self._auto_detect_model()
        
        payload = {
            "model": model_id,
            "messages": self._build_messages(messages),
            "temperature": temperature,
            "max_tokens": max_tokens or self.n_predict,
            "stream": True,
        }
        if self.repeat_penalty != 1.0:
            payload["repeat_penalty"] = self.repeat_penalty
        payload.update(kwargs)
        
        with client.stream("POST", "/v1/chat/completions", json=payload) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str == "[DONE]":
                    break
                try:
                    data = json_lib.loads(data_str)
                    delta = data.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        yield content
                except json_lib.JSONDecodeError:
                    continue
    
    def _auto_detect_model(self) -> str:
        """自动检测当前加载的模型"""
        try:
            client = self._get_client()
            resp = client.get("/v1/models", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                models = data.get("data", [])
                if models:
                    return models[0].get("id", "llama.cpp")
        except Exception as e:
            logger.debug(f"自动检测模型失败: {e}")
        return "llama.cpp"
    
    def list_models(self) -> list[ModelInfo]:
        """获取可用模型列表"""
        if self._models_cache is not None:
            return self._models_cache
        
        try:
            client = self._get_client()
            resp = client.get("/v1/models", timeout=10)
            resp.raise_for_status()
            data = resp.json()
            
            models = []
            for item in data.get("data", []):
                model_id = item.get("id", "")
                models.append(ModelInfo(
                    id=model_id,
                    name=model_id,
                    provider=self.PROVIDER_ID,
                    context_window=self.n_ctx,
                    max_output_tokens=self.n_predict,
                    supports_vision=True,  # llava 支持
                    supports_function_call=False,
                    supports_streaming=True,
                ))
            
            self._models_cache = models
            return models
        
        except Exception as e:
            logger.warning(f"获取 llama.cpp 模型列表失败: {e}")
            # 返回默认模型
            return [ModelInfo(
                id="llama.cpp",
                name="llama.cpp (本地)",
                provider=self.PROVIDER_ID,
                context_window=self.n_ctx,
            )]
    
    def get_model_info(self, model_id: str) -> ModelInfo | None:
        """获取模型详情"""
        models = self.list_models()
        for m in models:
            if m.id == model_id:
                return m
        return None
    
    # ============================================================
    # llama.cpp 特有功能
    # ============================================================
    
    def get_server_health(self) -> dict:
        """
        获取服务器健康状态。
        
        返回:
            {"status": "ok/loading/error", "slots": [...]}
        """
        try:
            client = self._get_client()
            resp = client.get("/health", timeout=5)
            if resp.status_code == 200:
                return resp.json()
            return {"status": "error", "code": resp.status_code}
        except httpx.ConnectError:
            return {"status": "unreachable", "error": "无法连接服务器"}
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    def get_slots_status(self) -> list[dict]:
        """
        获取槽位状态（并发处理能力）。
        
        返回:
            [{"id": 0, "state": "idle/processing", "task": {...}}, ...]
        """
        try:
            client = self._get_client()
            resp = client.get("/slots", timeout=5)
            if resp.status_code == 200:
                return resp.json()
            return []
        except Exception as e:
            logger.debug(f"获取槽位状态失败: {e}")
            return []
    
    def get_server_props(self) -> dict:
        """
        获取服务器属性（模型信息、配置等）。
        
        返回:
            {"model": "...", "n_ctx": 32768, ...}
        """
        if self._server_info_cache:
            return self._server_info_cache
        
        try:
            client = self._get_client()
            resp = client.get("/props", timeout=5)
            if resp.status_code == 200:
                self._server_info_cache = resp.json()
                return self._server_info_cache
            return {}
        except Exception as e:
            logger.debug(f"获取服务器属性失败: {e}")
            return {}
    
    def validate_config(self) -> tuple[bool, str]:
        """验证配置"""
        if not self.base_url:
            return False, "base_url 不能为空"
        return True, "配置有效"
    
    def test_connection(self) -> tuple[bool, str]:
        """测试连接"""
        health = self.get_server_health()
        status = health.get("status", "unknown")
        
        if status == "ok":
            props = self.get_server_props()
            model = props.get("model", "unknown")
            n_ctx = props.get("total_slots", props.get("n_ctx", "?"))
            return True, f"连接成功 | 模型: {model} | 上下文: {n_ctx}"
        elif status == "loading":
            return False, "服务器正在加载模型，请稍后"
        elif status == "unreachable":
            return False, f"无法连接到 {self.base_url}"
        else:
            return False, f"服务器状态异常: {health}"
    
    def close(self) -> None:
        """关闭客户端连接"""
        if self._client:
            self._client.close()
            self._client = None
