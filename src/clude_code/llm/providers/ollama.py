"""
Ollama 厂商（Ollama Provider）

本地 Ollama 服务支持。
"""

from __future__ import annotations

import logging

from ..base import ModelInfo, ProviderConfig
from ..registry import ProviderRegistry
from .openai_compat import OpenAICompatProvider

logger = logging.getLogger(__name__)


@ProviderRegistry.register("ollama")
class OllamaProvider(OpenAICompatProvider):
    """
    Ollama 本地厂商
    
    特点：
    - 无需 API Key
    - 支持动态模型列表（从本地服务获取）
    - 默认端口 11434
    """
    
    PROVIDER_NAME = "Ollama"
    PROVIDER_ID = "ollama"
    PROVIDER_TYPE = "local"
    REGION = "通用"
    
    # 常见模型（实际列表从服务动态获取）
    COMMON_MODELS = [
        ModelInfo(id="llama3.2", name="Llama 3.2", provider="ollama", context_window=131072),
        ModelInfo(id="llama3.1", name="Llama 3.1", provider="ollama", context_window=131072),
        ModelInfo(id="qwen2.5", name="Qwen 2.5", provider="ollama", context_window=32768),
        ModelInfo(id="qwen2.5-coder", name="Qwen 2.5 Coder", provider="ollama", context_window=32768),
        ModelInfo(id="deepseek-r1", name="DeepSeek R1", provider="ollama", context_window=64000),
        ModelInfo(id="gemma2", name="Gemma 2", provider="ollama", context_window=8192),
        ModelInfo(id="phi3", name="Phi 3", provider="ollama", context_window=4096),
        ModelInfo(id="mistral", name="Mistral", provider="ollama", context_window=32768),
        ModelInfo(id="codellama", name="Code Llama", provider="ollama", context_window=16384),
    ]
    
    def __init__(self, config: ProviderConfig):
        if not config.base_url:
            config.base_url = "http://127.0.0.1:11434"
        if not config.default_model:
            config.default_model = "llama3.2"
        # Ollama 不需要 API Key
        if not config.api_key:
            config.api_key = "ollama"
        super().__init__(config)
    
    def list_models(self) -> list[ModelInfo]:
        """从 Ollama 服务动态获取模型列表"""
        try:
            # Ollama 使用 /api/tags 而非标准 /v1/models
            import httpx
            resp = httpx.get(f"{self.base_url}/api/tags", timeout=10)
            resp.raise_for_status()
            data = resp.json()
            
            models = []
            for item in data.get("models", []):
                name = item.get("name", "")
                models.append(ModelInfo(
                    id=name,
                    name=name,
                    provider="ollama",
                    context_window=item.get("details", {}).get("context_length", 4096),
                ))
            return models if models else self.COMMON_MODELS
        except Exception as e:
            logger.warning(f"获取 Ollama 模型列表失败: {e}")
            return self.COMMON_MODELS
    
    def validate_config(self) -> tuple[bool, str]:
        if not self.base_url:
            return False, "Ollama base_url 不能为空"
        return True, "配置有效"

