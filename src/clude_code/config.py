from __future__ import annotations

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMConfig(BaseModel):
    provider: str = Field(default="llama_cpp_http")
    base_url: str = Field(default="http://127.0.0.1:8899")
    api_mode: str = Field(default="openai_compat")  # openai_compat | completion |ggml-org/gemma-3-12b-it-GGUF
	#aider --openai-api-base http://127.0.0.1:8899/v1 --openai-api-key no-key --model ggml-org/gemma-3-12b-it-GGUF
    #model: str = Field(default="GLM-4.6V-Flash-GGUF")  # llama.cpp may ignore; keep for compatibility
    #model: str = Field(default="ggml-org/gemma-3-12b-it-GGUF")  # llama.cpp may ignore; keep for compatibility   $env:AIDER_MODEL="ggml-org/gemma-3-12b-it-GGUF"
    model: str = Field(default="gemma-3-12b-it-Q4_K_M")  # llama.cpp may ignore; keep for compatibility   $env:AIDER_MODEL="ggml-org/gemma-3-4b-it-qat-GGUF"
    #model: str = Field(default="gemma-3-12b-it-GGUF")  # llama.cpp may ignore; keep for compatibility
    #model: str = Field(default="gemma-3-4b-it-qat-GGUF")  # llama.cpp may ignore; keep for compatibility
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_tokens: int = Field(default=409600, ge=1, le=8192, description="LLM 输出 token 限制（非上下文窗口大小，通常 512-2048 足够）") 
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
    level: str = Field(
        default="DEBUG",
        description="日志级别：DEBUG, INFO, WARNING, ERROR, CRITICAL。"
    )
    file_path: str = Field(
        default=".clude/logs/app.log",
        description="日志文件存储路径。"
    )
    max_bytes: int = Field(
        default=10_485_760,  # 10MB
        ge=1024,
        description="单个日志文件的最大字节数，超过后自动滚动。"
    )
    backup_count: int = Field(
        default=5,
        ge=0,
        description="保留的历史日志文件数量。"
    )
    log_format: str = Field(
        default="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        description="日志消息格式。"
    )
    date_format: str = Field(
        default="%Y-%m-%d %H:%M:%S",
        description="日志时间格式。"
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
    table_name: str = Field(
        default="code_chunks_v2",
        description="向量表名（用于 schema/策略演进与迁移；变更后会触发重新索引）。",
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

    # --- AST/tree-sitter 分块（业界推荐：函数/类/符号级 chunk） ---
    chunker: str = Field(
        default="heuristic",
        description="分块器：heuristic（默认，启发式）| tree_sitter（AST-aware，缺依赖时自动降级）。",
    )
    ts_max_node_lines: int = Field(default=220, ge=20, le=5000, description="tree-sitter 单个语法节点 chunk 最大行数（超过会再切分）。")
    ts_min_node_lines: int = Field(default=6, ge=1, le=200, description="tree-sitter 节点最小行数（太小的节点会被合并/跳过）。")
    ts_leading_context_lines: int = Field(default=2, ge=0, le=30, description="tree-sitter chunk 向上附带的注释/空行上下文行数（用于可读性）。")

    # --- P2-1: 并发索引优化 ---
    index_workers: int = Field(default=4, ge=1, le=16, description="并发索引线程数（1-16，推荐 4-8）。")


class WeatherConfig(BaseModel):
    """
    天气 API 配置（OpenWeatherMap）
    
    获取免费 API Key: https://openweathermap.org/api
    """
    enabled: bool = Field(default=True, description="是否启用天气工具。")
    api_key: str = Field(
        default="1959a5732178d790d56e0d313d1fe2e6",
        description="OpenWeatherMap API Key（必需）。也可通过环境变量 OPENWEATHERMAP_API_KEY 设置。"
    )
    default_units: str = Field(
        default="metric",
        description="默认温度单位：metric=摄氏度, imperial=华氏度, standard=开尔文。"
    )
    default_lang: str = Field(
        default="zh_cn",
        description="默认返回语言（zh_cn=中文, en=英文）。"
    )
    timeout_s: int = Field(
        default=10,
        ge=1,
        le=60,
        description="API 请求超时时间（秒）。"
    )
    cache_ttl_s: int = Field(
        default=300,
        ge=0,
        le=3600,
        description="天气数据缓存时间（秒，0=不缓存）。业界推荐 5-10 分钟避免频繁请求。"
    )
    log_to_file: bool = Field(
        default=True,
        description="是否将天气模块的日志写入文件。默认 True，写入 .clude/logs/app.log。"
    )


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
    weather: WeatherConfig = WeatherConfig()


