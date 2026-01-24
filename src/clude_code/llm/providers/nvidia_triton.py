"""
NVIDIA Triton Inference Server 提供商

文档: https://docs.nvidia.com/deeplearning/triton-inference-server/
"""

from __future__ import annotations

import logging
import os
from typing import Any

from ..base import LLMProvider, ModelInfo, ProviderConfig
from ..registry import ProviderRegistry
from ..llama_cpp_http import ChatMessage

logger = logging.getLogger(__name__)


@ProviderRegistry.register("nvidia_triton")
class NvidiaTritonProvider(LLMProvider):
    """
    NVIDIA Triton Inference Server 提供商。
    
    用于调用部署在 Triton 上的自定义模型。
    
    需要配置:
        - TRITON_SERVER_URL: Triton 服务地址 (如 http://localhost:8000)
        - TRITON_MODEL_NAME: 模型名称
    """
    
    PROVIDER_ID = "nvidia_triton"
    PROVIDER_NAME = "NVIDIA Triton"
    PROVIDER_TYPE = "local"
    REGION = "通用"
    
    def __init__(self, config: ProviderConfig | None = None):
        super().__init__(config)
        self._server_url = os.getenv("TRITON_SERVER_URL", "http://localhost:8000")
        self._model_name = os.getenv("TRITON_MODEL_NAME", "")
        self._model = config.default_model if config else self._model_name
    
    def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> str:
        """调用 Triton 推理服务"""
        import requests
        model_name = model or self._model_name
        
        if not model_name:
            raise ValueError("未配置 Triton 模型名称")
        
        # 构建输入（格式取决于模型配置）
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
        
        # Triton HTTP 推理请求格式
        inference_request = {
            "inputs": [
                {
                    "name": "text_input",
                    "shape": [1],
                    "datatype": "BYTES",
                    "data": [prompt],
                },
                {
                    "name": "max_tokens",
                    "shape": [1],
                    "datatype": "INT32",
                    "data": [max_tokens],
                },
                {
                    "name": "temperature",
                    "shape": [1],
                    "datatype": "FP32",
                    "data": [temperature],
                },
            ],
            "outputs": [
                {"name": "text_output"},
            ],
        }
        
        try:
            response = requests.post(
                f"{self._server_url}/v2/models/{model_name}/infer",
                json=inference_request,
                timeout=120,
            )
            response.raise_for_status()
            
            result = response.json()
            
            # 解析输出
            if "outputs" in result:
                for output in result["outputs"]:
                    if output["name"] == "text_output":
                        data = output.get("data", [])
                        if data:
                            return data[0] if isinstance(data[0], str) else str(data[0])
            
            return str(result)
            
        except Exception as e:
            logger.error(f"Triton 请求失败: {e}")
            raise
    
    def list_models(self) -> list[ModelInfo]:
        """列出可用模型（从 Triton 获取）"""
        import requests
        try:
            response = requests.get(
                f"{self._server_url}/v2/models",
                timeout=10,
            )
            response.raise_for_status()
            
            result = response.json()
            models = []
            
            for model in result.get("models", []):
                models.append(ModelInfo(
                    id=model["name"],
                    name=model["name"],
                    context_window=4096,  # 默认值
                ))
            
            return models
            
        except Exception as e:
            logger.warning(f"无法从 Triton 获取模型列表: {e}")
            if self._model_name:
                return [ModelInfo(
                    id=self._model_name,
                    name=self._model_name,
                    context_window=4096,
                )]
            return []
    
    def get_model_info(self, model_id: str) -> ModelInfo | None:
        """获取模型信息"""
        import requests
        try:
            response = requests.get(
                f"{self._server_url}/v2/models/{model_id}",
                timeout=10,
            )
            response.raise_for_status()
            
            result = response.json()
            return ModelInfo(
                id=model_id,
                name=result.get("name", model_id),
                context_window=4096,
            )
            
        except Exception:
            return None
    
    def set_model(self, model_id: str) -> None:
        """设置当前模型"""
        self._model_name = model_id
    
    def get_model(self) -> str:
        """获取当前模型"""
        return self._model_name or self._model

