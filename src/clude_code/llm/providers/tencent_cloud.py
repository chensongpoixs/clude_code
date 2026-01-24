"""
腾讯云（通用 LLM 服务）提供商

文档: https://cloud.tencent.com/document/product/1729
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
from datetime import datetime
from typing import Any

from ..base import LLMProvider, ModelInfo, ProviderConfig
from ..registry import ProviderRegistry
from ..llama_cpp_http import ChatMessage

logger = logging.getLogger(__name__)


@ProviderRegistry.register("tencent_cloud")
class TencentCloudProvider(LLMProvider):
    """
    腾讯云 LLM 提供商。
    
    需要配置:
        - TENCENT_SECRET_ID: 腾讯云 SecretId
        - TENCENT_SECRET_KEY: 腾讯云 SecretKey
    """
    
    PROVIDER_ID = "tencent_cloud"
    PROVIDER_NAME = "腾讯云"
    PROVIDER_TYPE = "cloud"
    REGION = "国内"
    BASE_URL = "https://hunyuan.tencentcloudapi.com"
    
    # 支持的模型（混元系列）
    MODELS = {
        "hunyuan-pro": ModelInfo(
            id="hunyuan-pro",
            name="混元 Pro",
            context_window=32000,
            supports_function_call=True,
        ),
        "hunyuan-standard": ModelInfo(
            id="hunyuan-standard",
            name="混元 Standard",
            context_window=32000,
        ),
        "hunyuan-lite": ModelInfo(
            id="hunyuan-lite",
            name="混元 Lite",
            context_window=4000,
        ),
        "hunyuan-turbo": ModelInfo(
            id="hunyuan-turbo",
            name="混元 Turbo",
            context_window=32000,
        ),
        "hunyuan-vision": ModelInfo(
            id="hunyuan-vision",
            name="混元 Vision",
            context_window=8000,
            supports_vision=True,
        ),
    }
    
    def __init__(self, config: ProviderConfig | None = None):
        super().__init__(config)
        self._secret_id = os.getenv("TENCENT_SECRET_ID", "")
        self._secret_key = os.getenv("TENCENT_SECRET_KEY", "")
        self._model = config.default_model if config else "hunyuan-pro"
    
    def _sign(self, params: dict, timestamp: int) -> str:
        """生成腾讯云 API 签名"""
        service = "hunyuan"
        host = "hunyuan.tencentcloudapi.com"
        algorithm = "TC3-HMAC-SHA256"
        
        date = datetime.utcfromtimestamp(timestamp).strftime("%Y-%m-%d")
        
        # CanonicalRequest
        http_request_method = "POST"
        canonical_uri = "/"
        canonical_querystring = ""
        ct = "application/json"
        payload = json.dumps(params)
        
        canonical_headers = f"content-type:{ct}\nhost:{host}\nx-tc-action:chatcompletions\n"
        signed_headers = "content-type;host;x-tc-action"
        hashed_request_payload = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        
        canonical_request = (
            f"{http_request_method}\n{canonical_uri}\n{canonical_querystring}\n"
            f"{canonical_headers}\n{signed_headers}\n{hashed_request_payload}"
        )
        
        # StringToSign
        credential_scope = f"{date}/{service}/tc3_request"
        hashed_canonical_request = hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()
        string_to_sign = f"{algorithm}\n{timestamp}\n{credential_scope}\n{hashed_canonical_request}"
        
        # Signature
        def _hmac_sha256(key: bytes, msg: str) -> bytes:
            return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()
        
        secret_date = _hmac_sha256(("TC3" + self._secret_key).encode("utf-8"), date)
        secret_service = _hmac_sha256(secret_date, service)
        secret_signing = _hmac_sha256(secret_service, "tc3_request")
        signature = hmac.new(secret_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
        
        # Authorization
        authorization = (
            f"{algorithm} Credential={self._secret_id}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )
        
        return authorization
    
    def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> str:
        """调用腾讯云混元"""
        import requests
        model_id = model or self._model
        
        # 转换消息格式
        tc_messages = []
        for msg in messages:
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            tc_messages.append({
                "Role": msg.role,
                "Content": content,
            })
        
        params = {
            "Model": model_id,
            "Messages": tc_messages,
            "TopP": 0.9,
            "Temperature": temperature,
        }
        
        timestamp = int(time.time())
        authorization = self._sign(params, timestamp)
        
        headers = {
            "Authorization": authorization,
            "Content-Type": "application/json",
            "Host": "hunyuan.tencentcloudapi.com",
            "X-TC-Action": "ChatCompletions",
            "X-TC-Timestamp": str(timestamp),
            "X-TC-Version": "2023-09-01",
        }
        
        try:
            response = requests.post(
                self.BASE_URL,
                headers=headers,
                json=params,
                timeout=120,
            )
            response.raise_for_status()
            
            result = response.json()
            
            if "Response" in result:
                resp = result["Response"]
                if "Error" in resp:
                    raise Exception(f"腾讯云 API 错误: {resp['Error']}")
                if "Choices" in resp and len(resp["Choices"]) > 0:
                    return resp["Choices"][0]["Message"]["Content"]
            
            return str(result)
            
        except Exception as e:
            logger.error(f"腾讯云请求失败: {e}")
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

