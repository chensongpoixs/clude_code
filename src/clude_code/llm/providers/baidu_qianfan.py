"""
百度千帆 (Baidu Qianfan) 提供商

文档: https://cloud.baidu.com/doc/WENXINWORKSHOP/
千帆大模型平台，提供文心一言等模型的 API 访问。
"""

from __future__ import annotations

import logging
import os
from typing import Any

from ..base import LLMProvider, ModelInfo, ProviderConfig
from ..registry import ProviderRegistry
from ..http_client import ChatMessage

logger = logging.getLogger(__name__)


@ProviderRegistry.register("baidu_qianfan")
class BaiduQianfanProvider(LLMProvider):
    """
    百度千帆 (Baidu Qianfan) 提供商。
    
    需要配置:
        - QIANFAN_AK: 千帆 Access Key
        - QIANFAN_SK: 千帆 Secret Key
    
    或:
        - QIANFAN_ACCESS_TOKEN: 直接使用 Access Token
    """
    
    PROVIDER_ID = "baidu_qianfan"
    PROVIDER_NAME = "百度千帆"
    PROVIDER_TYPE = "cloud"
    REGION = "国内"
    BASE_URL = "https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat"
    TOKEN_URL = "https://aip.baidubce.com/oauth/2.0/token"
    
    # 模型与端点映射
    MODEL_ENDPOINTS = {
        "ernie-bot-4": "completions_pro",
        "ernie-bot-8k": "ernie_bot_8k",
        "ernie-bot-turbo": "eb-instant",
        "ernie-speed-128k": "ernie-speed-128k",
        "ernie-lite-8k": "ernie-lite-8k",
        "ernie-tiny-8k": "ernie-tiny-8k",
    }
    
    # 支持的模型
    MODELS = {
        "ernie-bot-4": ModelInfo(
            id="ernie-bot-4",
            name="文心一言 4.0",
            context_window=5120,
            supports_function_call=True,
        ),
        "ernie-bot-8k": ModelInfo(
            id="ernie-bot-8k",
            name="文心一言 8K",
            context_window=8192,
        ),
        "ernie-bot-turbo": ModelInfo(
            id="ernie-bot-turbo",
            name="文心一言 Turbo",
            context_window=7168,
        ),
        "ernie-speed-128k": ModelInfo(
            id="ernie-speed-128k",
            name="ERNIE Speed 128K",
            context_window=128000,
        ),
        "ernie-lite-8k": ModelInfo(
            id="ernie-lite-8k",
            name="ERNIE Lite 8K",
            context_window=8192,
        ),
    }
    
    def __init__(self, config: ProviderConfig | None = None):
        super().__init__(config)
        self._ak = os.getenv("QIANFAN_AK", "")
        self._sk = os.getenv("QIANFAN_SK", "")
        self._access_token = os.getenv("QIANFAN_ACCESS_TOKEN", "")
        self._model = config.default_model if config else "ernie-bot-4"
    
    def _get_access_token(self) -> str:
        """获取 Access Token"""
        import requests
        if self._access_token:
            return self._access_token
        
        if not self._ak or not self._sk:
            raise ValueError("未配置千帆 AK/SK 或 Access Token")
        
        params = {
            "grant_type": "client_credentials",
            "client_id": self._ak,
            "client_secret": self._sk,
        }
        
        response = requests.post(self.TOKEN_URL, params=params, timeout=10)
        response.raise_for_status()
        
        result = response.json()
        self._access_token = result["access_token"]
        return self._access_token
    
    def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> str:
        """调用千帆"""
        import requests
        model_id = model or self._model
        endpoint = self.MODEL_ENDPOINTS.get(model_id, "completions_pro")
        
        # 获取 token
        access_token = self._get_access_token()
        
        # 转换消息格式
        qf_messages = []
        system_content = ""
        
        for msg in messages:
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            if msg.role == "system":
                system_content = content
            else:
                qf_messages.append({
                    "role": msg.role,
                    "content": content,
                })
        
        payload = {
            "messages": qf_messages,
            "temperature": temperature,
        }
        
        if system_content:
            payload["system"] = system_content
        
        try:
            response = requests.post(
                f"{self.BASE_URL}/{endpoint}?access_token={access_token}",
                json=payload,
                timeout=120,
            )
            response.raise_for_status()
            
            result = response.json()
            
            if "error_code" in result:
                raise Exception(f"千帆 API 错误: {result}")
            
            return result.get("result", str(result))
            
        except Exception as e:
            logger.error(f"千帆请求失败: {e}")
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

