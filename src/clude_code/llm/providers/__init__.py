"""
LLM 厂商实现（LLM Provider Implementations）

支持 50+ 厂商，覆盖国际主流、国内合规、本地私有化及算力推理平台。

每个厂商一个独立文件，通过装饰器自动注册到 ProviderRegistry。

厂商列表：
- 国际主流：OpenAI, Anthropic, Google Gemini, Mistral, Cohere
- 云厂商：Azure OpenAI, AWS Bedrock
- 国内厂商：DeepSeek, 月之暗面, 智谱, 通义千问, 文心一言, 百川, MiniMax, 讯飞, 腾讯混元
- 推理平台：Ollama, Groq, Together.ai, OpenRouter, SiliconFlow
- 本地部署：llama.cpp, Ollama
- 聚合平台：OpenRouter
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# 所有厂商模块（按类别组织）
_PROVIDER_MODULES = [
    # 默认本地（优先加载）
    "llama_cpp",          # llama.cpp（默认）
    "openai_compat",      # 通用 OpenAI 兼容
    
    # 国际主流
    "openai",             # OpenAI
    "anthropic",          # Anthropic / Claude
    "google_gemini",      # Google Gemini
    "mistral",            # Mistral AI
    "cohere",             # Cohere
    
    # 云厂商
    "azure_openai",       # Azure OpenAI
    "google_vertex",      # Google Cloud Vertex AI
    "aws_bedrock",        # AWS Bedrock
    "aws_sagemaker",      # AWS SageMaker
    "tencent_cloud",      # 腾讯云
    
    # NVIDIA 系列
    "nvidia_nim",         # NVIDIA NIM
    "nvidia_triton",      # NVIDIA Triton
    "nvidia_catalog",     # NVIDIA API Catalog
    
    # 国内厂商
    "deepseek",           # DeepSeek
    "moonshot",           # 月之暗面 / Kimi
    "zhipu",              # 智谱 AI / ChatGLM
    "qianwen",            # 通义千问 / Tongyi
    "wenxin",             # 文心一言 / ERNIE
    "baichuan",           # 百川智能
    "minimax",            # MiniMax
    "spark",              # 讯飞星火
    "hunyuan",            # 腾讯混元
    "stepfun",            # 阶跃星辰
    "modelscope",         # 魔搭社区
    "baidu_qianfan",      # 百度千帆
    "alibaba_pai",        # 阿里云 PAI
    "tencent_ti",         # 腾讯云 TI
    "qiniu",              # 七牛云
    
    # 推理平台
    "ollama",             # Ollama（本地）
    "groq",               # Groq（超快推理）
    "together",           # Together.ai
    "openrouter",         # OpenRouter（聚合）
    "siliconflow",        # 硅基流动
    "replicate",          # Replicate
    "huggingface",        # Hugging Face
    "lepton",             # Lepton AI
    "novita",             # novita.ai
    "jina",               # Jina AI
    "gpustack",           # GPUStack
    "perfxcloud",         # PerfXCloud
    "xorbits",            # Xorbits Inference
    
    # 本地/私有化
    "localai",            # LocalAI
    "xinference",         # Xinference
    "openllm",            # OpenLLM
    "text_embedding",     # Text Embedding Inference
]


def _auto_import_providers() -> None:
    """自动导入所有厂商模块（触发装饰器注册）"""
    import importlib
    
    success_count = 0
    fail_count = 0
    
    for module_name in _PROVIDER_MODULES:
        try:
            importlib.import_module(f".{module_name}", package=__name__)
            logger.debug(f"已加载厂商模块: {module_name}")
            success_count += 1
        except ImportError as e:
            logger.warning(f"加载厂商模块失败: {module_name} - {e}")
            fail_count += 1
    
    logger.info(f"厂商模块加载完成: {success_count} 成功, {fail_count} 失败")


# 模块加载时自动导入厂商
_auto_import_providers()


# 导出列表
__all__ = [
    "LlamaCppProvider",
    "OpenAICompatProvider",
    "OpenAIProvider",
    "AnthropicProvider",
    "GoogleGeminiProvider",
    "MistralProvider",
    "CohereProvider",
    "AzureOpenAIProvider",
    "DeepSeekProvider",
    "MoonshotProvider",
    "ZhipuProvider",
    "QianwenProvider",
    "WenxinProvider",
    "BaichuanProvider",
    "MiniMaxProvider",
    "SparkProvider",
    "HunyuanProvider",
    "OllamaProvider",
    "GroqProvider",
    "TogetherProvider",
    "OpenRouterProvider",
    "SiliconFlowProvider",
]
