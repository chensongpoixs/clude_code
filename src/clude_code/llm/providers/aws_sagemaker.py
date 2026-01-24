"""
AWS SageMaker 提供商

文档: https://docs.aws.amazon.com/sagemaker/
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


@ProviderRegistry.register("aws_sagemaker")
class AWSSageMakerProvider(LLMProvider):
    """
    AWS SageMaker 提供商。
    
    用于调用部署在 SageMaker 上的自定义模型端点。
    
    需要配置:
        - AWS_ACCESS_KEY_ID: AWS 访问密钥
        - AWS_SECRET_ACCESS_KEY: AWS 密钥
        - AWS_DEFAULT_REGION: 区域
        - SAGEMAKER_ENDPOINT_NAME: SageMaker 端点名称
    """
    
    PROVIDER_ID = "aws_sagemaker"
    PROVIDER_NAME = "AWS SageMaker"
    PROVIDER_TYPE = "cloud"
    REGION = "海外"
    
    def __init__(self, config: ProviderConfig | None = None):
        super().__init__(config)
        self._region = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
        self._endpoint_name = os.getenv("SAGEMAKER_ENDPOINT_NAME", "")
        self._model = config.default_model if config else "sagemaker-endpoint"
        self._client = None
    
    def _ensure_client(self) -> Any:
        """确保 SageMaker Runtime 客户端已初始化"""
        if self._client is not None:
            return self._client
        
        try:
            import boto3
            self._client = boto3.client(
                "sagemaker-runtime",
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
        """调用 SageMaker 端点"""
        client = self._ensure_client()
        endpoint_name = model or self._endpoint_name
        
        if not endpoint_name:
            raise ValueError("未配置 SageMaker 端点名称")
        
        # 构建输入（通用格式，实际格式取决于部署的模型）
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
        
        # 构建请求体（HuggingFace TGI 格式）
        body = {
            "inputs": prompt,
            "parameters": {
                "max_new_tokens": max_tokens,
                "temperature": temperature,
                "do_sample": temperature > 0,
            },
        }
        
        try:
            response = client.invoke_endpoint(
                EndpointName=endpoint_name,
                ContentType="application/json",
                Accept="application/json",
                Body=json.dumps(body),
            )
            
            response_body = json.loads(response["Body"].read())
            
            # 解析响应（格式取决于模型）
            if isinstance(response_body, list) and len(response_body) > 0:
                result = response_body[0]
                if isinstance(result, dict) and "generated_text" in result:
                    return result["generated_text"]
                return str(result)
            elif isinstance(response_body, dict):
                if "generated_text" in response_body:
                    return response_body["generated_text"]
                if "outputs" in response_body:
                    return response_body["outputs"]
            
            return str(response_body)
            
        except Exception as e:
            logger.error(f"SageMaker 请求失败: {e}")
            raise
    
    def list_models(self) -> list[ModelInfo]:
        """列出可用模型（SageMaker 端点）"""
        # SageMaker 端点是自定义的，返回配置的端点
        if self._endpoint_name:
            return [
                ModelInfo(
                    id=self._endpoint_name,
                    name=f"SageMaker: {self._endpoint_name}",
                    context_window=4096,
                )
            ]
        return []
    
    def get_model_info(self, model_id: str) -> ModelInfo | None:
        """获取模型信息"""
        if model_id == self._endpoint_name:
            return ModelInfo(
                id=model_id,
                name=f"SageMaker: {model_id}",
                context_window=4096,
            )
        return None
    
    def set_model(self, model_id: str) -> None:
        """设置当前端点"""
        self._endpoint_name = model_id
    
    def get_model(self) -> str:
        """获取当前端点"""
        return self._endpoint_name or self._model

