from __future__ import annotations

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMConfig(BaseModel):
    provider: str = Field(default="llama_cpp_http")
    base_url: str = Field(default="http://127.0.0.1:8899")
    api_mode: str = Field(default="openai_compat")  # openai_compat | completion |ggml-org/gemma-3-12b-it-GGUF
	#aider --openai-api-base http://127.0.0.1:8899/v1 --openai-api-key no-key --model ggml-org/gemma-3-12b-it-GGUF
    model: str = Field(default="ggml-org/gemma-3-12b-it-GGUF")  # llama.cpp may ignore; keep for compatibility   $env:AIDER_MODEL="ggml-org/gemma-3-12b-it-GGUF"
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_tokens: int = Field(default=409600, ge=1)  # 配置LLM返回数据最大长度  你的预期文本长度是多少？ 
    timeout_s: int = Field(default=120, ge=1)


class PolicyConfig(BaseModel):
    allow_network: bool = False
    confirm_write: bool = True
    confirm_exec: bool = True
    allowed_tools: list[str] = Field(
        default_factory=list,
        description="允许的工具名单（空=不限制）。对标 Claude Code 的 allowedTools。",
    )
    disallowed_tools: list[str] = Field(
        default_factory=list,
        description="禁止的工具名单。对标 Claude Code 的 disallowedTools。",
    )


class LimitsConfig(BaseModel):
    max_output_bytes: int = Field(default=1_000_000, ge=1024)
    max_file_read_bytes: int = Field(default=1_000_000, ge=1024)


class LoggingConfig(BaseModel):
    """日志系统配置。"""
    log_to_console: bool = Field(
        default=True,
        description="是否将日志输出到控制台（默认 True，同时输出到控制台和文件）"
    )

class OrchestratorConfig(BaseModel):
    """编排层配置（阶段 3：规划-执行）。"""
    enable_planning: bool = Field(
        default=True,
        description="是否启用显式规划（Plan -> Execute）。默认开启。",
    )
    max_plan_steps: int = Field(default=12, ge=1, le=30, description="单次计划最大步骤数（避免计划过长）。")
    # 说明：
    # - 该值用于单步“迭代次数”熔断（见 execution.py 的 for iteration in range(max_step_tool_calls)）
    # - 早期误将上限写成 le=50，导致用户配置为 100 时加载失败（与默认值冲突）
    max_step_tool_calls: int = Field(default=100, ge=1, le=500, description="单个步骤内最大工具调用次数（防止死循环）。")
    max_replans: int = Field(default=2, ge=0, le=10, description="最大重规划次数（验证失败/卡住时）。")
    planning_retry: int = Field(default=1, ge=0, le=5, description="计划解析失败的重试次数。")


class RAGConfig(BaseModel):
    """RAG (Retrieval-Augmented Generation) 配置。"""
    enabled: bool = Field(default=True, description="是否启用向量检索。")
    device: str = Field(
        default="cpu",
        description="本地计算设备：'cpu', 'cuda' (Nvidia), 'mps' (Apple Silicon)。"
    )
    embedding_model: str = Field(
        default="BAAI/bge-small-zh-v1.5",
        description="本地 Embedding 模型名称（由 fastembed 加载）。"
    )
    model_cache_dir: str | None = Field(
        default="D:/LLM/llm/Embedding/",  #默认目录 None值
        description="本地 Embedding 模型缓存/加载路径。如果为 None，则使用 fastembed 默认路径。"
    )
    db_path: str = Field(
        default=".clude/vector_db",
        description="向量数据库存储路径。"
    )
    chunk_size: int = Field(default=500, description="代码分块大小（字符数）。")
    chunk_overlap: int = Field(default=50, description="分块重叠大小。")

    # --- Phase D+: RAG 索引深度调优（业界标配项） ---
    scan_interval_s: int = Field(default=30, ge=5, le=3600, description="后台索引扫描间隔（秒）。")
    max_file_bytes: int = Field(default=2_000_000, ge=10_000, description="单文件最大索引大小（字节），超过则跳过。")
    embed_batch_size: int = Field(default=64, ge=1, le=4096, description="Embedding 批处理大小（越大越快但更吃内存）。")
    chunk_target_lines: int = Field(default=40, ge=5, le=500, description="启发式分块目标行数（优先在空行/定义边界切分）。")
    chunk_max_lines: int = Field(default=60, ge=5, le=2000, description="启发式分块最大行数（硬上限）。")
    chunk_overlap_lines: int = Field(default=5, ge=0, le=200, description="分块行重叠（提升跨块召回稳定性）。")


class CludeConfig(BaseSettings):
    """
    Config priority (high -> low):
    - environment variables (prefix CLUDE_)
    - config file (passed by CLI; loaded manually)
    - defaults
    """

    model_config = SettingsConfigDict(env_prefix="CLUDE_", extra="ignore")

    workspace_root: str = "."
    llm: LLMConfig = LLMConfig()
    policy: PolicyConfig = PolicyConfig()
    limits: LimitsConfig = LimitsConfig()
    logging: LoggingConfig = LoggingConfig()
    orchestrator: OrchestratorConfig = OrchestratorConfig()
    rag: RAGConfig = RAGConfig()


