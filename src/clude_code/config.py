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


