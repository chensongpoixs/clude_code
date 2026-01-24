"""
LLM 客户端与适配器（LLM Clients and Adapters）

支持多厂商接入：
- llama.cpp / Ollama / vLLM（本地）
- OpenAI / Anthropic / Azure（国际）
- DeepSeek / Moonshot / 智谱（国内）
"""

from __future__ import annotations

import importlib
import sys

from .http_client import ChatMessage, LlamaCppHttpClient
from .image_utils import (
    load_image_from_path,
    load_image_from_url,
    extract_images_from_text,
    build_multimodal_content,
    convert_to_openai_vision_format,
)
from .base import LLMProvider, ModelInfo, ProviderConfig
from .registry import ProviderRegistry, get_provider, list_providers, has_provider
from .model_manager import ModelManager, get_model_manager
from .cost_tracker import CostTracker, get_cost_tracker, UsageRecord, CostSummary
from .failover import FailoverManager, FailoverConfig, AllProvidersFailedError
from .auto_router import AutoRouter, TaskType, Priority, RoutingDecision, auto_select_model, get_auto_router

# 自动加载厂商实现
from . import providers  # noqa: F401

# ------------------------------------------------------------------
# Backward-compat module alias
# - 目的：删除物理文件 `llama_cpp_http.py` 后仍允许旧 import 路径工作
# - 行为：import clude_code.llm.llama_cpp_http 等价于 import clude_code.llm.http_client
# ------------------------------------------------------------------
_legacy_mod_name = __name__ + ".llama_cpp_http"
if _legacy_mod_name not in sys.modules:
    sys.modules[_legacy_mod_name] = importlib.import_module(__name__ + ".http_client")

__all__ = [
    # 原有导出
    "ChatMessage",
    "LlamaCppHttpClient",
    "load_image_from_path",
    "load_image_from_url",
    "extract_images_from_text",
    "build_multimodal_content",
    "convert_to_openai_vision_format",
    # 基础类
    "LLMProvider",
    "ModelInfo",
    "ProviderConfig",
    "ProviderRegistry",
    "get_provider",
    "list_providers",
    "has_provider",
    "ModelManager",
    "get_model_manager",
    # 成本追踪
    "CostTracker",
    "get_cost_tracker",
    "UsageRecord",
    "CostSummary",
    # 故障转移
    "FailoverManager",
    "FailoverConfig",
    "AllProvidersFailedError",
    # 自动路由
    "AutoRouter",
    "TaskType",
    "Priority",
    "RoutingDecision",
    "auto_select_model",
    "get_auto_router",
]
