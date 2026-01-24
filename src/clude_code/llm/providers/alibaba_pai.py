"""
阿里云 PAI (Platform for AI) 提供商

文档: https://help.aliyun.com/product/30347.html
"""

from __future__ import annotations

import logging
import os
from typing import Any

from ..base import LLMProvider, ModelInfo, ProviderConfig
from ..registry import ProviderRegistry
from ..llama_cpp_http import ChatMessage

logger = logging.getLogger(__name__)


@ProviderRegistry.register("alibaba_pai")
class AlibabaPAIProvider(LLMProvider):
    """
    阿里云 PAI 提供商。
    
    用于调用部署在阿里云 PAI-EAS 上的模型服务。
    
    需要配置:
        - ALIBABA_CLOUD_ACCESS_KEY_ID: 阿里云 AccessKey ID
        - ALIBABA_CLOUD_ACCESS_KEY_SECRET: 阿里云 AccessKey Secret
        - PAI_EAS_ENDPOINT: PAI-EAS 服务端点
        - PAI_EAS_SERVICE_NAME: 服务名称
    """
    
    PROVIDER_ID = "alibaba_pai"
    PROVIDER_NAME = "阿里云 PAI-EAS"
    PROVIDER_TYPE = "cloud"
    REGION = "国内"
    
    def __init__(self, config: ProviderConfig | None = None):
        super().__init__(config)
        self._access_key_id = os.getenv("ALIBABA_CLOUD_ACCESS_KEY_ID", "")
        self._access_key_secret = os.getenv("ALIBABA_CLOUD_ACCESS_KEY_SECRET", "")
        self._endpoint = os.getenv("PAI_EAS_ENDPOINT", "")
        self._service_name = os.getenv("PAI_EAS_SERVICE_NAME", "")
        self._model = config.default_model if config else self._service_name
    
    def _sign_request(self, method: str, path: str, headers: dict, body: str) -> str:
        """生成阿里云 API 签名"""
        # 简化签名实现
        string_to_sign = f"{method}\n{headers.get('Content-Type', '')}\n{headers.get('Date', '')}\n{path}"
        signature = hmac.new(
            self._access_key_secret.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            hashlib.sha1,
        ).hexdigest()
        return signature
    
    def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> str:
        """调用 PAI-EAS 服务"""
        import requests
        if not self._endpoint or not self._service_name:
            raise ValueError("未配置 PAI-EAS 端点或服务名称")
        
        # 构建 prompt
        prompt_parts = []
        for msg in messages:
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            if msg.role == "system":
                prompt_parts.append(f"<|system|>\n{content}")
            elif msg.role == "user":
                prompt_parts.append(f"<|user|>\n{content}")
            else:
                prompt_parts.append(f"<|assistant|>\n{content}")
        
        prompt_parts.append("<|assistant|>")
        prompt = "\n".join(prompt_parts)
        
        # 构建请求
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"{self._access_key_id}",
        }
        
        payload = {
            "prompt": prompt,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        
        try:
            response = requests.post(
                f"{self._endpoint}/api/predict/{self._service_name}",
                headers=headers,
                json=payload,
                timeout=120,
            )
            response.raise_for_status()
            
            result = response.json()
            
            # 解析响应（格式取决于部署的模型）
            if isinstance(result, dict):
                if "generated_text" in result:
                    return result["generated_text"]
                if "response" in result:
                    return result["response"]
                if "output" in result:
                    return result["output"]
            
            return str(result)
            
        except Exception as e:
            logger.error(f"PAI-EAS 请求失败: {e}")
            raise
    
    def list_models(self) -> list[ModelInfo]:
        """列出可用模型（返回配置的服务）"""
        if self._service_name:
            return [ModelInfo(
                id=self._service_name,
                name=f"PAI-EAS: {self._service_name}",
                context_window=4096,
            )]
        return []
    
    def get_model_info(self, model_id: str) -> ModelInfo | None:
        """获取模型信息"""
        if model_id == self._service_name:
            return ModelInfo(
                id=model_id,
                name=f"PAI-EAS: {model_id}",
                context_window=4096,
            )
        return None
    
    def set_model(self, model_id: str) -> None:
        """设置当前服务"""
        self._service_name = model_id
    
    def get_model(self) -> str:
        """获取当前服务"""
        return self._service_name or self._model

