"""
{厂商名称} 提供商（{Provider Name} Provider）

新增厂商模板文件 - 复制此文件并重命名为 `{provider_id}.py`

文档: {官方 API 文档链接}

## 使用说明

1. 复制此文件为 `{your_provider}.py`
2. 替换所有 `{placeholder}` 为实际值
3. 实现 `chat()` 方法
4. 可选实现 `chat_async()` 和 `chat_stream()`
5. 运行测试验证

## 命名规范

- 文件名: `{provider}.py` 或 `{vendor}_{product}.py`
- PROVIDER_ID 必须与文件名一致（不含 .py）
- 类名: `{ProviderName}Provider`（PascalCase）
"""

from __future__ import annotations

import logging
import os
from typing import Any, Iterator, TYPE_CHECKING

from ..base import LLMProvider, ModelInfo, ProviderConfig
from ..registry import ProviderRegistry

if TYPE_CHECKING:
    from ..http_client import ChatMessage

logger = logging.getLogger(__name__)


# ============================================================
# 注册厂商（装饰器方式）
# - 参数必须与文件名一致
# - 装饰器会在模块导入时自动注册
# ============================================================
@ProviderRegistry.register("your_provider")  # TODO: 改为实际 provider_id
class YourProvider(LLMProvider):  # TODO: 改为实际类名，如 MyCloudProvider
    """
    {厂商名称} 提供商。
    
    配置示例:
        providers:
          your_provider:
            api_key: "sk-xxx"
            base_url: "https://api.example.com"
            default_model: "model-name"
    
    环境变量:
        YOUR_PROVIDER_API_KEY: API 密钥
        YOUR_PROVIDER_BASE_URL: 服务端点（可选）
    """
    
    # ========== 必填类属性 ==========
    PROVIDER_ID = "your_provider"         # 必须与文件名和装饰器参数一致
    PROVIDER_NAME = "Your Provider"       # 显示名称（支持中文）
    PROVIDER_TYPE = "cloud"               # cloud | local | aggregator
    REGION = "海外"                       # 海外 | 国内 | 通用
    
    # ========== 可选类属性 ==========
    DEFAULT_BASE_URL = "https://api.example.com/v1"
    DEFAULT_MODEL = "default-model"
    DEFAULT_TIMEOUT = 120
    
    # 预定义模型列表（可选）
    MODELS = {
        "model-a": ModelInfo(
            id="model-a",
            name="Model A",
            provider="your_provider",
            context_window=8192,
            max_output_tokens=4096,
            supports_vision=False,
            supports_function_call=False,
        ),
        "model-b": ModelInfo(
            id="model-b",
            name="Model B (Vision)",
            provider="your_provider",
            context_window=32768,
            supports_vision=True,
        ),
    }
    
    def __init__(self, config: ProviderConfig):
        """
        初始化厂商。
        
        Args:
            config: 厂商配置（来自 .clude.yaml 或环境变量）
        """
        super().__init__(config)
        
        # 从配置或环境变量获取凭证
        self.api_key = config.api_key or os.environ.get("YOUR_PROVIDER_API_KEY", "")
        self.base_url = (config.base_url or os.environ.get("YOUR_PROVIDER_BASE_URL") or self.DEFAULT_BASE_URL).rstrip("/")
        self.timeout = config.timeout_s or self.DEFAULT_TIMEOUT
        
        # 初始化 HTTP 客户端（延迟创建）
        self._client = None
    
    def _get_client(self):
        """获取或创建 HTTP 客户端（延迟初始化）"""
        if self._client is None:
            import httpx
            self._client = httpx.Client(
                base_url=self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=self.timeout,
            )
        return self._client
    
    def _build_messages(self, messages: list["ChatMessage"]) -> list[dict]:
        """将 ChatMessage 转换为 API 格式"""
        result = []
        for msg in messages:
            if isinstance(msg.content, str):
                result.append({"role": msg.role, "content": msg.content})
            else:
                # 多模态内容
                result.append({"role": msg.role, "content": msg.content})
        return result
    
    # ========== 必须实现的方法 ==========
    
    def chat(
        self,
        messages: list["ChatMessage"],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> str:
        """
        同步聊天（必须实现）。
        
        Args:
            messages: 消息列表
            model: 模型 ID（可选，使用默认模型）
            temperature: 温度参数
            max_tokens: 最大输出 token
            **kwargs: 其他 API 参数
        
        Returns:
            助手回复文本
        
        Raises:
            RuntimeError: API 调用失败
        """
        import httpx
        
        client = self._get_client()
        model_id = model or self._model or self.DEFAULT_MODEL
        
        payload = {
            "model": model_id,
            "messages": self._build_messages(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
            **kwargs,
        }
        
        try:
            resp = client.post("/chat/completions", json=payload)
            
            if resp.status_code >= 400:
                logger.error(f"{self.PROVIDER_NAME} API 错误: {resp.status_code} - {resp.text[:200]}")
                raise RuntimeError(f"{self.PROVIDER_NAME} 请求失败: HTTP {resp.status_code}")
            
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        
        except httpx.TimeoutException:
            raise RuntimeError(f"{self.PROVIDER_NAME} 请求超时（{self.timeout}s）")
        except httpx.ConnectError:
            raise RuntimeError(f"无法连接到 {self.PROVIDER_NAME}: {self.base_url}")
    
    async def chat_async(
        self,
        messages: list["ChatMessage"],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> str:
        """异步聊天（必须实现）"""
        import httpx
        
        model_id = model or self._model or self.DEFAULT_MODEL
        
        payload = {
            "model": model_id,
            "messages": self._build_messages(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
            **kwargs,
        }
        
        async with httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=self.timeout,
        ) as client:
            resp = await client.post("/chat/completions", json=payload)
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
        """流式聊天（必须实现）"""
        import json
        
        client = self._get_client()
        model_id = model or self._model or self.DEFAULT_MODEL
        
        payload = {
            "model": model_id,
            "messages": self._build_messages(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
            **kwargs,
        }
        
        with client.stream("POST", "/chat/completions", json=payload) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                data_str = line[6:]
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
        # 方式 1: 返回预定义列表
        if self.MODELS:
            return list(self.MODELS.values())
        
        # 方式 2: 从 API 获取（如果支持）
        try:
            client = self._get_client()
            resp = client.get("/models")
            resp.raise_for_status()
            data = resp.json()
            
            models = []
            for item in data.get("data", []):
                models.append(ModelInfo(
                    id=item.get("id", ""),
                    name=item.get("name", item.get("id", "")),
                    provider=self.PROVIDER_ID,
                ))
            return models
        except Exception as e:
            logger.warning(f"获取模型列表失败: {e}")
            return [ModelInfo(
                id=self.DEFAULT_MODEL,
                name=self.PROVIDER_NAME,
                provider=self.PROVIDER_ID,
            )]
    
    # ========== 可选方法 ==========
    
    def validate_config(self) -> tuple[bool, str]:
        """验证配置是否有效"""
        if not self.api_key:
            return False, "缺少 API Key"
        if not self.base_url:
            return False, "缺少 base_url"
        return True, "配置有效"
    
    def test_connection(self) -> tuple[bool, str]:
        """测试连接是否正常"""
        try:
            models = self.list_models()
            return True, f"连接成功，可用模型: {len(models)} 个"
        except Exception as e:
            return False, f"连接失败: {e}"
    
    def close(self) -> None:
        """关闭客户端（释放资源）"""
        if self._client:
            self._client.close()
            self._client = None


# ============================================================
# 注意事项
# ============================================================
# 
# 1. 装饰器 @ProviderRegistry.register("xxx") 中的 ID 必须与文件名一致
# 2. PROVIDER_ID 类属性也必须与文件名一致
# 3. 需要 requests/httpx 时使用延迟导入（在方法内 import）
# 4. 敏感信息（API Key）不要硬编码，从配置/环境变量获取
# 5. 所有 API 调用需要异常处理
# 6. 超时时间建议使用配置项
#
# ============================================================

