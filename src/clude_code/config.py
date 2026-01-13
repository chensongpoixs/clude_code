from __future__ import annotations

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMConfig(BaseModel):
    provider: str = Field(default="llama_cpp_http")
    base_url: str = Field(default="http://127.0.0.1:8899")
    api_mode: str = Field(default="openai_compat")  # openai_compat | completion |ggml-org/gemma-3-12b-it-GGUF
    model: str = Field(default="")  # llama.cpp may ignore; keep for compatibility
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1024, ge=1)
    timeout_s: int = Field(default=120, ge=1)


class PolicyConfig(BaseModel):
    allow_network: bool = False
    confirm_write: bool = True
    confirm_exec: bool = True


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
    max_plan_steps: int = Field(default=8, ge=1, le=30, description="单次计划最大步骤数（避免计划过长）。")
    max_step_tool_calls: int = Field(default=12, ge=1, le=50, description="单个步骤内最大工具调用次数（防止死循环）。")
    max_replans: int = Field(default=2, ge=0, le=10, description="最大重规划次数（验证失败/卡住时）。")
    planning_retry: int = Field(default=1, ge=0, le=5, description="计划解析失败的重试次数。")


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


