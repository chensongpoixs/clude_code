from __future__ import annotations

"""
/**
 * @author chensong（chensong）
 * @date 2026-01-19
 * @brief 全局配置系统（Global Configuration System）
 *
 * 背景与目的（Background & Purpose）：
 * - 统一管理 clude-code 的所有可配置参数（LLM/Policy/RAG/Tooling/Logging）。
 * - 配置优先级遵循：环境变量（Environment Variables） > 配置文件（YAML Config File） > 代码默认值（Code Defaults）。
 *
 * 关键约束（Key Constraints）：
 * - 禁止在模块内硬编码敏感信息（Sensitive Info），例如 API Key/Token。
 * - 禁止使用 print 进行日志输出，必须使用 logger（Logger）。
 *
 * 配置文件位置（Config Location）：
 * - 主配置：~/.clude/.clude.yaml
 * - 兼容读取：./.clude/.clude.yaml、./clude.yaml
 */
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from collections import OrderedDict

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    yaml = None  # type: ignore
    YAML_AVAILABLE = False


_logger = logging.getLogger(__name__)

"""
大模型配置（LLM Configuration）
@author chensong（chensong）
@date 2026-01-19
@brief 大模型配置（LLM Configuration）
"""
class LLMConfig(BaseModel):
    provider: str = Field(default="llama_cpp_http")
    base_url: str = Field(default="http://127.0.0.1:8899")
    api_mode: str = Field(default="openai_compat")  # openai_compat | completion
    # Aider（代码助手）对接 llama.cpp OpenAI 兼容接口（OpenAI Compatible API）示例：
    # aider --openai-api-base http://127.0.0.1:8899/v1 --openai-api-key no-key --model ggml-org/gemma-3-12b-it-GGUF
    #model: str = Field(default="GLM-4.6V-Flash-GGUF")  # llama.cpp may ignore; keep for compatibility
    #model: str = Field(default="ggml-org/gemma-3-12b-it-GGUF")  # llama.cpp may ignore; keep for compatibility   $env:AIDER_MODEL="ggml-org/gemma-3-12b-it-GGUF"
    #model: str = Field(default="gemma-3-12b-it-Q4_K_M")  # llama.cpp may ignore; keep for compatibility   $env:AIDER_MODEL="ggml-org/gemma-3-4b-it-qat-GGUF"
    #model: str = Field(default="gemma-3-1b-it-f16")  # llama.cpp may ignore; keep for compatibility   $env:AIDER_MODEL="gemma-3-4b-it-qat-GGUF"
    #model: str = Field(default="gemma-3-4b-it-f16")  # llama.cpp may ignore; keep for compatibility   $env:AIDER_MODEL="gemma-3-4b-it-qat-GGUF"
    #model: str = Field(default="gemma-3-4b-it-Q4_K_M")  # llama.cpp may ignore; keep for compatibility   $env:AIDER_MODEL="gemma-3-4b-it-qat-GGUF"
    model: str = Field(default="gemma-3-12b-it-GGUF")  # llama.cpp may ignore; keep for compatibility
   # model: str = Field(default="gpt-oss-20b-mxfp4")  # llama.cpp may ignore; keep for compatibility
    #model: str = Field(default="Qwen3-8B-Q4_K_M")  # llama.cpp may ignore; keep for compatibility
    #model: str = Field(default="gemma-3-4b-it-qat-GGUF")  # llama.cpp may ignore; keep for compatibility
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    # max_tokens 是“单次输出上限”，不同后端可支持更大范围；这里不强行限制到 8k，
    # 避免用户在 .clude/.clude.yaml 中配置更大值时直接触发校验失败。
    # REM  context 128K = 131072
    # REM  context 32K  == 32768
    max_tokens: int = Field(
        default=409600,
        ge=1,
        le=409600,
        description="LLM 单次输出 token 上限（非上下文窗口大小）。常见推荐 512-4096；如后端支持可设更大。",
    )
    timeout_s: int = Field(default=120, ge=1)

"""
策略配置（Policy Configuration）
@author chensong（chensong）
@date 2026-01-19
@brief 策略配置（Policy Configuration）
"""
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

"""
资源限制配置（Limits Configuration）
@author chensong（chensong）
@date 2026-01-19
@brief 资源限制配置（Limits Configuration）
"""
class LimitsConfig(BaseModel):
    max_output_bytes: int = Field(default=1_000_000, ge=1024)
    max_file_read_bytes: int = Field(default=1_000_000, ge=1024)

"""
日志系统配置（Logging Configuration）
@author chensong（chensong）
@date 2026-01-19
@brief 日志系统配置（Logging Configuration）
"""
class LoggingConfig(BaseModel):
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

"""
LLM 详细日志配置（LLM Detail Logging）
@author chensong（chensong）
@date 2026-01-19
@brief LLM 请求/返回日志：仅打印本次新增 user 与本次返回（避免历史轮次刷屏）
"""
class LLMDetailLoggingConfig(BaseModel):
    enabled: bool = Field(default=True, description="是否启用 LLM 请求/返回日志。")
    scope: str = Field(
        default="per_request",
        description="打印范围：per_request=每次请求仅打印本次新增 user；per_turn=整轮累计打印。",
    )
    log_to_file: bool = Field(default=True, description="是否写入 file_only_logger。")
    log_to_console: bool = Field(default=True, description="是否输出到控制台 logger。")
    include_params: bool = Field(default=True, description="请求日志是否包含 model/api_mode/max_tokens/base_url 摘要。")
    include_tool_call: bool = Field(default=True, description="返回日志是否包含 tool_call（如存在）。")
    max_user_chars: int = Field(default=20000, ge=0, description="单条 user 最大打印字符数（0=不截断）。")
    max_response_chars: int = Field(default=20000, ge=0, description="assistant_text 最大打印字符数（0=不截断）。")
    include_caller: bool = Field(default=True, description="是否打印调用方（module.func + file:line）。")
    call_flow_enabled: bool = Field(default=True, description="是否实时打印 LLM 调用流程（CALL_START/CALL_END）。")
    call_flow_summary: bool = Field(default=False, description="turn 结束时是否打印调用流程汇总（默认关闭）。")

"""
编排层配置（Orchestrator Configuration）
@author chensong（chensong）
@date 2026-01-19
@brief 编排层配置（Orchestrator Configuration）
"""
class OrchestratorConfig(BaseModel):

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

"""
RAG 配置（Retrieval-Augmented Generation Configuration）
@author chensong（chensong）
@date 2026-01-19
@brief RAG 配置（Retrieval-Augmented Generation Configuration）
"""
class RAGConfig(BaseModel):
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


# 从工具配置模块导入（统一管理）
from clude_code.config.tools_config import (
    WeatherToolConfig,
    FileToolConfig,
    DirectoryToolConfig,
    CommandToolConfig,
    SearchToolConfig,
    WebToolConfig,
    PatchToolConfig,
    DisplayToolConfig,
    QuestionToolConfig,
    RepoMapToolConfig,
    SkillToolConfig,
    TaskToolConfig,
)

# 向后兼容：保留 WeatherConfig 作为别名
WeatherConfig = WeatherToolConfig

"""
UI 用户偏好配置（UI Preferences）
@author chensong（chensong）
@date 2026-01-19
@brief UI 用户偏好配置（UI Preferences）
"""
class UIConfig(BaseModel):

    theme: str = Field(default="default", description="主题：default, dark, light")
    color_scheme: str = Field(default="vibrant", description="配色方案：vibrant, minimal, high_contrast")
    refresh_rate: int = Field(default=12, ge=1, le=60, description="Live 界面刷新率（Hz）")
    show_animations: bool = Field(default=True, description="是否显示动画效果")
    show_icons: bool = Field(default=True, description="是否显示状态图标")
    compact_mode: bool = Field(default=False, description="紧凑模式（减少空行）")
    layout: str = Field(default="default", description="布局模式：default, split, grid")

    # 快捷键配置（键: 功能名）
    shortcuts: Dict[str, str] = Field(default_factory=dict, description="自定义快捷键映射")

"""
编辑器相关配置（Editor Configuration）
@author chensong（chensong）
@date 2026-01-19
@brief 编辑器相关配置（Editor Configuration）
"""
class EditorConfig(BaseModel):
    preferred_editor: str = Field(default="auto", description="首选编辑器：auto, vim, nano, vscode")
    line_numbers: bool = Field(default=True, description="是否显示行号")
    syntax_highlighting: bool = Field(default=True, description="是否启用语法高亮")
    auto_save: bool = Field(default=True, description="是否自动保存")
    tab_size: int = Field(default=4, ge=2, le=8, description="制表符大小")

"""
历史记录配置（History Configuration）
@author chensong（chensong）
@date 2026-01-19
@brief 历史记录配置（History Configuration）
"""
class HistoryConfig(BaseModel):
    max_history_size: int = Field(default=1000, ge=100, le=10000, description="最大历史记录数")
    history_file: str = Field(default="~/.clude/history.json", description="历史记录文件路径")
    save_history: bool = Field(default=True, description="是否保存历史记录")
    search_enabled: bool = Field(default=True, description="是否启用历史搜索")

"""
全局配置（Clude Global Configuration）
@author chensong（chensong）
@date 2026-01-19
@brief 全局配置（Clude Global Configuration）
"""
class CludeConfig(BaseSettings):

    model_config = SettingsConfigDict(
        env_prefix="CLUDE_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    @classmethod
    def settings_customise_sources(  # type: ignore[override]
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        """
        配置优先级（高 -> 低）：
        - init_settings（代码显式传参）
        - env_settings（环境变量 CLUDE_）
        - dotenv_settings（.env 等）
        - config file（~/.clude/.clude.yaml，兼容读取工作区/旧文件名）
        - file_secret_settings
        - defaults（字段默认值）

        说明：之前使用 __init__ 注入文件配置会导致“配置文件优先级高于环境变量”，
        与我们期望（env > file）冲突；这里用 settings sources 正确实现优先级。
        """

        def yaml_file_settings() -> Dict[str, Any]:
            try:
                return _load_config_from_file()
            except Exception as e:
                _logger.warning(
                    "读取 YAML 配置失败，将使用默认/环境变量配置: %s",
                    e,
                    exc_info=True,
                )
                return {}

        # 目标优先级：init > env > dotenv > file > secrets > defaults
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            yaml_file_settings,
            file_secret_settings,
        )

    workspace_root: str = "."
    llm: LLMConfig = LLMConfig()
    policy: PolicyConfig = PolicyConfig()
    limits: LimitsConfig = LimitsConfig()
    logging: LoggingConfig = LoggingConfig()
    llm_detail_logging: LLMDetailLoggingConfig = LLMDetailLoggingConfig()
    orchestrator: OrchestratorConfig = OrchestratorConfig()
    rag: RAGConfig = RAGConfig()

    # 工具模块配置
    weather: WeatherToolConfig = WeatherToolConfig()
    file: FileToolConfig = FileToolConfig()
    directory: DirectoryToolConfig = DirectoryToolConfig()
    command: CommandToolConfig = CommandToolConfig()
    search: SearchToolConfig = SearchToolConfig()
    web: WebToolConfig = WebToolConfig()
    patch: PatchToolConfig = PatchToolConfig()
    display: DisplayToolConfig = DisplayToolConfig()
    question: QuestionToolConfig = QuestionToolConfig()
    repo_map: RepoMapToolConfig = RepoMapToolConfig()
    skill: SkillToolConfig = SkillToolConfig()
    task: TaskToolConfig = TaskToolConfig()

"""
扩展配置（Extended Configuration）
@author chensong（chensong）
@date 2026-01-19
@brief 扩展配置（Extended Configuration）
"""
class ExtendedCludeConfig(CludeConfig):

    # 新增配置
    ui: UIConfig = Field(default_factory=UIConfig)
    editor: EditorConfig = Field(default_factory=EditorConfig)
    history: HistoryConfig = Field(default_factory=HistoryConfig)

"""
配置管理器（Config Manager）
@author chensong（chensong）
@date 2026-01-19
@brief 配置管理器（Config Manager）
"""
class ConfigManager:

    # 约定：Python 禁止类体 Docstring；本行用于避免后续“声明前注释块”被解释为 class __doc__
    _NO_CLASS_DOCSTRING: bool = True

    """
    初始化配置管理器（Init Config Manager）
    @brief 负责配置的加载、保存、导入导出与运行时更新（Config Load/Save/Update）
    """
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = Path(config_path) if config_path else self._get_default_config_path()
        self.config = self._load_config()

    """
    获取默认配置文件路径（Get Default Config Path）
    @brief 主配置文件固定为用户目录 ~/.clude/.clude.yaml
    """
    def _get_default_config_path(self) -> Path:
        # 主配置文件位置固定为用户目录：~/.clude/.clude.yaml
        # 说明：工作区 .clude/.clude.yaml 仅作为 CludeConfig 的兼容读取来源，
        # ConfigManager 的“可编辑配置”统一落在用户目录，避免多份配置导致困惑。
        return Path.home() / ".clude" / ".clude.yaml"

    """
    加载配置文件（Load Config）
    @brief 支持 YAML 为主，JSON 为历史兼容；失败时回退到代码默认值
    """
    def _load_config(self) -> ExtendedCludeConfig:
        try:
            if self.config_path.exists():
                suffix = self.config_path.suffix.lower()

                # YAML 优先
                if suffix in {".yaml", ".yml"}:
                    with open(self.config_path, "r", encoding="utf-8") as f:
                        data = yaml.safe_load(f) or {}
                    return ExtendedCludeConfig(**data)

                # JSON 兼容（历史格式）
                if suffix == ".json":
                    with open(self.config_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    return ExtendedCludeConfig(**data)

                # 未知后缀：先 YAML 再 JSON
                try:
                    with open(self.config_path, "r", encoding="utf-8") as f:
                        data = yaml.safe_load(f) or {}
                    return ExtendedCludeConfig(**data)
                except Exception:
                    with open(self.config_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    return ExtendedCludeConfig(**data)
            else:
                # 创建默认配置（纯代码默认值，不受 env / file 影响）
                config = ExtendedCludeConfig.model_construct()
                # 先尝试保存，如果失败则静默跳过
                try:
                    self._save_config(config)
                except Exception:
                    pass  # 保存失败时不影响程序运行
                return config
        except Exception as e:
            _logger.warning("加载配置文件失败，使用默认配置: %s", e, exc_info=True)
            # 纯代码默认值，不受 env / file 影响
            return ExtendedCludeConfig.model_construct()

    """
    保存配置到文件（Save Config）
    @brief 默认写 YAML，并通过模板渲染保留中文注释；仅显式 .json 才写 JSON
    """
    def _save_config(self, config: ExtendedCludeConfig) -> None:
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            data = config.model_dump()

            suffix = self.config_path.suffix.lower()

            # 统一写 YAML（推荐），仅当用户明确指定 .json 时写 JSON（兼容）
            if suffix in {".yaml", ".yml", ""}:
                text = _render_commented_yaml(data)
                self.config_path.write_text(text, encoding="utf-8")
            elif suffix == ".json":
                # 兼容：显式指定 .json 才允许写 JSON
                with open(self.config_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False, default=str)
            else:
                # 未知后缀：默认按 YAML 写
                text = _render_commented_yaml(data)
                self.config_path.write_text(text, encoding="utf-8")
        except Exception as e:
            _logger.warning("保存配置文件失败: %s", e, exc_info=True)

    """
    保存当前配置（Save Current Config）
    """
    def save_config(self) -> None:
        self._save_config(self.config)

    """
    重新加载配置（Reload Config）
    """
    def reload_config(self) -> None:
        self.config = self._load_config()

    """
    获取当前配置（Get Current Config）
    """
    def get_config(self) -> ExtendedCludeConfig:
        return self.config

    """
    更新配置项（Update Config Value）
    @param key_path 配置路径（如 ui.theme / llm.model）
    @param value 新值（New Value）
    """
    def update_config(self, key_path: str, value: Any) -> None:
        try:
            keys = key_path.split('.')
            obj = self.config

            # 遍历到倒数第二级
            for key in keys[:-1]:
                if hasattr(obj, key):
                    obj = getattr(obj, key)
                else:
                    raise ValueError(f"配置路径不存在: {'.'.join(keys[:keys.index(key)+1])}")

            # 设置最终值
            if hasattr(obj, keys[-1]):
                setattr(obj, keys[-1], value)
                self.save_config()
            else:
                raise ValueError(f"配置项不存在: {key_path}")

        except Exception as e:
            raise ValueError(f"更新配置失败: {e}")

    """
    获取配置值（Get Config Value）
    @param key_path 配置路径（如 ui.theme / llm.model）
    @return 配置值（Config Value）
    """
    def get_config_value(self, key_path: str) -> Any:
        try:
            keys = key_path.split('.')
            obj = self.config

            for key in keys:
                if hasattr(obj, key):
                    obj = getattr(obj, key)
                else:
                    raise ValueError(f"配置路径不存在: {key_path}")

            return obj

        except Exception as e:
            raise ValueError(f"获取配置失败: {e}")

    """
    重置为默认配置（Reset To Defaults）
    @brief 纯代码默认值：不受 env/file 影响（符合规范 3.2 默认值来源）
    """
    def reset_to_defaults(self) -> None:
        # 纯代码默认值：不受 env / file 影响（符合规范 3.2 “默认值来源”）
        self.config = ExtendedCludeConfig.model_construct()
        self.save_config()

    """
    导出配置（Export Config）
    @param export_path 导出路径；为空则返回字符串（YAML 文本）
    """
    def export_config(self, export_path: Optional[str] = None) -> str:
        data = self.config.model_dump()

        if export_path:
            export_file = Path(export_path)
            export_file.parent.mkdir(parents=True, exist_ok=True)
            with open(export_file, 'w', encoding='utf-8') as f:
                # 优先使用YAML格式
                if YAML_AVAILABLE:
                    f.write(_render_commented_yaml(data))
                else:
                    json.dump(data, f, indent=2, ensure_ascii=False, default=str)
            return str(export_file)
        else:
            # 返回字符串格式
            if YAML_AVAILABLE:
                return _render_commented_yaml(data)
            else:
                return json.dumps(data, indent=2, ensure_ascii=False, default=str)

    """
    导入配置（Import Config）
    @param import_path 导入文件路径（YAML/JSON）
    """
    def import_config(self, import_path: str) -> None:
        import_file = Path(import_path)
        if not import_file.exists():
            raise FileNotFoundError(f"配置文件不存在: {import_path}")

        # 尝试从YAML文件加载
        data = None
        try:
            if YAML_AVAILABLE:
                with open(import_file, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f) or {}
            else:
                with open(import_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
        except Exception:
            # 如果YAML/JSON加载失败，尝试另一种格式
            try:
                with open(import_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except Exception:
                raise ValueError(f"无法解析配置文件格式: {import_path}")

        try:
            self.config = ExtendedCludeConfig(**data)
            self.save_config()
        except Exception as e:
            raise ValueError(f"导入配置失败，配置格式错误: {e}")

    """
    验证配置有效性（Validate Config）
    @return 是否有效（True/False）
    """
    def validate_config(self) -> bool:
        try:
            # 尝试创建配置对象来验证
            ExtendedCludeConfig(**self.config.model_dump())
            return True
        except Exception:
            return False

    """
    获取配置摘要（Get Config Summary）
    @return 摘要字典（Summary Dict）
    """
    def get_config_summary(self) -> Dict[str, Any]:
        return {
            "config_file": str(self.config_path),
            "config_valid": self.validate_config(),
            "ui_theme": self.config.ui.theme,
            "animations_enabled": self.config.ui.show_animations,
            "compact_mode": self.config.ui.compact_mode,
            "model": self.config.llm.model,
            "workspace": self.config.workspace_root,
        }


# 全局配置管理器实例
_config_manager: Optional[ConfigManager] = None


"""
获取全局配置管理器实例（Get Global Config Manager）
"""
def get_config_manager() -> ConfigManager:
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager


"""
初始化全局配置管理器（Init Global Config Manager）
"""
def init_config_manager(config_path: Optional[str] = None) -> ConfigManager:
    global _config_manager
    _config_manager = ConfigManager(config_path)
    return _config_manager


"""
查找配置文件（Find Config File）
@brief 搜索顺序：~/.clude/.clude.yaml → ~/.clude/.clude.yml → ./.clude/.clude.yaml → ./.clude/.clude.yml → ./clude.yaml → ./clude.yml
"""
def _find_config_file() -> Optional[Path]:
    home = Path.home()
    search_paths = [
        home / ".clude" / ".clude.yaml",
        home / ".clude" / ".clude.yml",
        Path(".clude/.clude.yaml"),
        Path(".clude/.clude.yml"),
        Path("clude.yaml"),  # 向后兼容
        Path("clude.yml"),   # 向后兼容
    ]

    for path in search_paths:
        if path.exists() and path.is_file():
            return path

    return None


"""
从 YAML 文件加载配置（Load YAML Config）
"""
def _load_yaml_config(config_path: Path) -> Dict[str, Any]:
    if not YAML_AVAILABLE:
        raise ImportError("PyYAML is not installed. Install with: pip install PyYAML")

    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f) or {}

"""从文件加载配置（如果存在的话）

Returns:
    从文件加载的配置字典
"""
def _load_config_from_file() -> Dict[str, Any]:

    config_file = _find_config_file()
    if config_file:
        try:
            return _load_yaml_config(config_file)
        except Exception as e:
            # 如果加载失败，返回空字典，使用默认配置；同时给出可观测的告警
            _logger.warning("加载配置文件失败（%s），将使用默认配置: %s", config_file, e, exc_info=True)

    return {}


"""
生成 YAML 顶层 key 顺序（Order Top-level YAML Keys）
@brief 按 .clude/.clude.example.yaml 的顺序输出，保证可读性与一致性
"""
def _order_top_level_keys_for_yaml(data: Dict[str, Any]) -> Dict[str, Any]:
    preferred_order = [
        # 额外字段：如果存在，放到最前（示例文件未包含，但项目配置包含）
        "workspace_root",
        # 与示例文件一致的顺序
        "llm",
        "policy",
        "limits",
        "logging",
        "llm_detail_logging",
        "orchestrator",
        "rag",
        # 工具模块配置（与示例一致）
        "weather",
        "file",
        "directory",
        "command",
        "search",
        "web",
        "patch",
        "display",
        "question",
        "repo_map",
        "skill",
        "task",
    ]

    ordered: "OrderedDict[str, Any]" = OrderedDict()
    for k in preferred_order:
        if k in data:
            ordered[k] = data[k]

    # 追加剩余 key（保持原有插入顺序）
    for k, v in data.items():
        if k not in ordered:
            ordered[k] = v

    return dict(ordered)


"""
定位仓库根目录（Find Repo Root）
@brief 用于读取 .clude/.clude.example.yaml 注释模板
"""
def _get_repo_root() -> Optional[Path]:
    try:
        # .../src/clude_code/config/config.py -> parents: config, clude_code, src, repo_root
        return Path(__file__).resolve().parents[3]
    except Exception:
        return None


"""
渲染单行 YAML 标量（Render YAML Scalar）
"""
def _yaml_inline_scalar(value: Any) -> str:
    if not YAML_AVAILABLE:
        return str(value)
    dumped = yaml.safe_dump(
        value,
        allow_unicode=True,
        default_flow_style=True,
        sort_keys=False,
    ).strip()
    # safe_dump 对标量一般是单行；保险起见只取第一行
    return dumped.splitlines()[0] if dumped else ""


def _get_by_path(data: Dict[str, Any], path: list[str]) -> Any:
    cur: Any = data
    for k in path:
        if not isinstance(cur, dict) or k not in cur:
            return None
        cur = cur[k]
    return cur


"""
拆分值与行尾注释（Split Value & Comment）
@brief 处理 `: xxx  # comment` 形式（适用于模板渲染）
"""
def _split_value_and_comment(rest: str) -> tuple[str, str]:
    if "#" not in rest:
        return rest.rstrip(), ""
    idx = rest.find("#")
    return rest[:idx].rstrip(), rest[idx:].rstrip()


"""
生成带中文注释的 YAML 文本（Render Commented YAML）
@brief 以 `.clude/.clude.example.yaml` 为模板按路径替换值，保留注释与顺序
"""
def _render_commented_yaml(data: Dict[str, Any]) -> str:
    ordered_data = _order_top_level_keys_for_yaml(data)

    repo_root = _get_repo_root()
    template_path = (repo_root / ".clude" / ".clude.example.yaml") if repo_root else None
    template_text = None
    if template_path and template_path.exists():
        try:
            template_text = template_path.read_text(encoding="utf-8")
        except Exception:
            template_text = None

    if not template_text:
        # 兜底：没有模板就输出无注释 YAML（仍保持 key 顺序）
        return yaml.safe_dump(
            ordered_data,
            indent=2,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
        )

    lines = template_text.splitlines()
    out: list[str] = []
    stack: list[tuple[int, str]] = []

    for line in lines:
        stripped = line.lstrip(" ")
        if not stripped or stripped.startswith("#"):
            out.append(line)
            continue
        if ":" not in stripped:
            out.append(line)
            continue

        indent = len(line) - len(stripped)
        key, rest = stripped.split(":", 1)

        # 维护路径栈：同级/回退时出栈
        while stack and stack[-1][0] >= indent:
            stack.pop()

        value_part, comment_part = _split_value_and_comment(rest)
        value_part = value_part.strip()

        path = [k for _, k in stack] + [key]

        # map 节点（如 `llm:`）
        if value_part == "":
            out.append(line)
            stack.append((indent, key))
            continue

        # scalar/list 节点：如果 data 有对应值则替换
        v = _get_by_path(ordered_data, path)
        if v is not None:
            rendered = _yaml_inline_scalar(v)
            new_line = (" " * indent) + f"{key}: {rendered}"
            if comment_part:
                new_line += " " + comment_part.lstrip()
            out.append(new_line)
        else:
            out.append(line)

    # 如果 workspace_root 不在模板中，但在数据里：在文件顶部插入中文注释+字段
    if "workspace_root" in ordered_data and "workspace_root:" not in template_text:
        ws = _yaml_inline_scalar(ordered_data["workspace_root"])
        prefix = [
            "# 工作区根目录（可选；不配置时默认当前目录）",
            f"workspace_root: {ws}",
            "",
        ]
        out = prefix + out

    return "\n".join(out).rstrip() + "\n"


