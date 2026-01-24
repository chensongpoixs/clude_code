"""
AWS Bedrock 提供商

文档: https://docs.aws.amazon.com/bedrock/
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from ..base import LLMProvider, ModelInfo, ProviderConfig
from ..registry import ProviderRegistry
from ..llama_cpp_http import ChatMessage

logger = logging.getLogger(__name__)


@ProviderRegistry.register("aws_bedrock")
class AWSBedrockProvider(LLMProvider):
    """
    AWS Bedrock 提供商。
    
    需要配置:
        - AWS_ACCESS_KEY_ID: AWS 访问密钥
        - AWS_SECRET_ACCESS_KEY: AWS 密钥
        - AWS_DEFAULT_REGION: 区域 (如 us-east-1)
    
    或使用 AWS CLI 配置的默认凭证。
    """
    
    PROVIDER_ID = "aws_bedrock"
    PROVIDER_NAME = "AWS Bedrock"
    PROVIDER_TYPE = "cloud"
    REGION = "海外"
    
    # 支持的模型
    MODELS = {
        "anthropic.claude-3-5-sonnet-20241022-v2:0": ModelInfo(
            id="anthropic.claude-3-5-sonnet-20241022-v2:0",
            name="Claude 3.5 Sonnet v2",
            context_window=200000,
            supports_vision=True,
            supports_function_call=True,
        ),
        "anthropic.claude-3-haiku-20240307-v1:0": ModelInfo(
            id="anthropic.claude-3-haiku-20240307-v1:0",
            name="Claude 3 Haiku",
            context_window=200000,
            supports_vision=True,
        ),
        "amazon.titan-text-premier-v1:0": ModelInfo(
            id="amazon.titan-text-premier-v1:0",
            name="Amazon Titan Text Premier",
            context_window=32000,
        ),
        "amazon.titan-text-express-v1": ModelInfo(
            id="amazon.titan-text-express-v1",
            name="Amazon Titan Text Express",
            context_window=8000,
        ),
        "meta.llama3-70b-instruct-v1:0": ModelInfo(
            id="meta.llama3-70b-instruct-v1:0",
            name="Llama 3 70B Instruct",
            context_window=8000,
        ),
        "mistral.mistral-large-2407-v1:0": ModelInfo(
            id="mistral.mistral-large-2407-v1:0",
            name="Mistral Large",
            context_window=128000,
            supports_function_call=True,
        ),
        "cohere.command-r-plus-v1:0": ModelInfo(
            id="cohere.command-r-plus-v1:0",
            name="Cohere Command R+",
            context_window=128000,
            supports_function_call=True,
        ),
    }
    
    def __init__(self, config: ProviderConfig | None = None):
        super().__init__(config)
        self._region = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
        self._model = config.default_model if config else "anthropic.claude-3-5-sonnet-20241022-v2:0"
        self._client = None
    
    def _ensure_client(self) -> Any:
        """确保 Bedrock 客户端已初始化"""
        if self._client is not None:
            return self._client
        
        try:
            import boto3
            self._client = boto3.client(
                "bedrock-runtime",
                region_name=self._region,
            )
            return self._client
        except ImportError:
            raise ImportError("需要安装 boto3: pip install boto3")
    
    def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> str:
        """调用 Bedrock 生成"""
        client = self._ensure_client()
        model_id = model or self._model
        
        # 转换消息格式
        bedrock_messages = []
        system_prompt = ""
        
        for msg in messages:
            if msg.role == "system":
                system_prompt = msg.content if isinstance(msg.content, str) else str(msg.content)
                continue
            
            role = "user" if msg.role == "user" else "assistant"
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            bedrock_messages.append({"role": role, "content": content})
        
        # 构建请求体（Anthropic 格式）
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": bedrock_messages,
        }
        
        if system_prompt:
            body["system"] = system_prompt
        
        try:
            response = client.invoke_model(
                modelId=model_id,
                body=json.dumps(body),
                contentType="application/json",
                accept="application/json",
            )
            
            response_body = json.loads(response["body"].read())
            
            # 解析响应
            if "content" in response_body:
                return response_body["content"][0]["text"]
            elif "completion" in response_body:
                return response_body["completion"]
            else:
                return str(response_body)
                
        except Exception as e:
            logger.error(f"Bedrock 请求失败: {e}")
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

