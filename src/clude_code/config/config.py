from __future__ import annotations

import json
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
    # max_tokens 是“单次输出上限”，不同后端可支持更大范围；这里不强行限制到 8k，
    # 避免用户在 .clude/.clude.yaml 中配置更大值时直接触发校验失败。
    max_tokens: int = Field(
        default=409600,
        ge=1,
        le=409600,
        description="LLM 单次输出 token 上限（非上下文窗口大小）。常见推荐 512-4096；如后端支持可设更大。",
    )
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


class UIConfig(BaseModel):
    """UI 用户偏好配置"""
    theme: str = Field(default="default", description="主题：default, dark, light")
    color_scheme: str = Field(default="vibrant", description="配色方案：vibrant, minimal, high_contrast")
    refresh_rate: int = Field(default=12, ge=1, le=60, description="Live 界面刷新率（Hz）")
    show_animations: bool = Field(default=True, description="是否显示动画效果")
    show_icons: bool = Field(default=True, description="是否显示状态图标")
    compact_mode: bool = Field(default=False, description="紧凑模式（减少空行）")
    layout: str = Field(default="default", description="布局模式：default, split, grid")

    # 快捷键配置（键: 功能名）
    shortcuts: Dict[str, str] = Field(default_factory=dict, description="自定义快捷键映射")


class EditorConfig(BaseModel):
    """编辑器相关配置"""
    preferred_editor: str = Field(default="auto", description="首选编辑器：auto, vim, nano, vscode")
    line_numbers: bool = Field(default=True, description="是否显示行号")
    syntax_highlighting: bool = Field(default=True, description="是否启用语法高亮")
    auto_save: bool = Field(default=True, description="是否自动保存")
    tab_size: int = Field(default=4, ge=2, le=8, description="制表符大小")


class HistoryConfig(BaseModel):
    """历史记录配置"""
    max_history_size: int = Field(default=1000, ge=100, le=10000, description="最大历史记录数")
    history_file: str = Field(default="~/.clude/history.json", description="历史记录文件路径")
    save_history: bool = Field(default=True, description="是否保存历史记录")
    search_enabled: bool = Field(default=True, description="是否启用历史搜索")


class CludeConfig(BaseSettings):
    """
    Config priority (high -> low):
    - environment variables (prefix CLUDE_)
    - config file (auto-loaded from .clude/.clude.yaml)
    - defaults
    """

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
        - config file（.clude/.clude.yaml）
        - file_secret_settings
        - defaults（字段默认值）

        说明：之前使用 __init__ 注入文件配置会导致“配置文件优先级高于环境变量”，
        与我们期望（env > file）冲突；这里用 settings sources 正确实现优先级。
        """

        def yaml_file_settings() -> Dict[str, Any]:
            try:
                return _load_config_from_file()
            except Exception as e:
                print(f"警告：读取 YAML 配置失败，将使用默认/环境变量配置: {e}")
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


class ExtendedCludeConfig(CludeConfig):
    """扩展的配置类，包含UI和其他用户偏好"""

    # 新增配置
    ui: UIConfig = Field(default_factory=UIConfig)
    editor: EditorConfig = Field(default_factory=EditorConfig)
    history: HistoryConfig = Field(default_factory=HistoryConfig)


class ConfigManager:
    """配置管理器，负责配置的加载、保存和运行时更新"""

    def __init__(self, config_path: Optional[str] = None):
        """初始化配置管理器

        Args:
            config_path: 配置文件路径，如果为None则使用默认路径
        """
        self.config_path = Path(config_path) if config_path else self._get_default_config_path()
        self.config = self._load_config()

    def _get_default_config_path(self) -> Path:
        """获取默认配置文件路径"""
        # 主配置文件位置固定为用户目录：~/.clude/.clude.yaml
        # 说明：工作区 .clude/.clude.yaml 仅作为 CludeConfig 的兼容读取来源，
        # ConfigManager 的“可编辑配置”统一落在用户目录，避免多份配置导致困惑。
        return Path.home() / ".clude" / ".clude.yaml"

    def _load_config(self) -> ExtendedCludeConfig:
        """加载配置文件"""
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
            print(f"警告：加载配置文件失败，使用默认配置: {e}")
            # 纯代码默认值，不受 env / file 影响
            return ExtendedCludeConfig.model_construct()

    def _save_config(self, config: ExtendedCludeConfig) -> None:
        """保存配置到文件"""
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
            print(f"警告：保存配置文件失败: {e}")

    def save_config(self) -> None:
        """保存当前配置"""
        self._save_config(self.config)

    def reload_config(self) -> None:
        """重新加载配置"""
        self.config = self._load_config()

    def get_config(self) -> ExtendedCludeConfig:
        """获取当前配置"""
        return self.config

    def update_config(self, key_path: str, value: Any) -> None:
        """更新配置项（支持嵌套路径）

        Args:
            key_path: 配置路径，如 "ui.theme" 或 "llm.model"
            value: 新值
        """
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

    def get_config_value(self, key_path: str) -> Any:
        """获取配置值（支持嵌套路径）

        Args:
            key_path: 配置路径，如 "ui.theme" 或 "llm.model"

        Returns:
            配置值
        """
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

    def reset_to_defaults(self) -> None:
        """重置为默认配置"""
        self.config = ExtendedCludeConfig()
        self.save_config()

    def export_config(self, export_path: Optional[str] = None) -> str:
        """导出配置到文件

        Args:
            export_path: 导出路径，如果为None则返回字符串

        Returns:
            如果export_path为None，返回配置字符串，否则返回文件路径
        """
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

    def import_config(self, import_path: str) -> None:
        """从文件导入配置

        Args:
            import_path: 导入文件路径
        """
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

    def validate_config(self) -> bool:
        """验证当前配置是否有效

        Returns:
            True if valid, False otherwise
        """
        try:
            # 尝试创建配置对象来验证
            ExtendedCludeConfig(**self.config.model_dump())
            return True
        except Exception:
            return False

    def get_config_summary(self) -> Dict[str, Any]:
        """获取配置摘要"""
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


def get_config_manager() -> ConfigManager:
    """获取全局配置管理器实例"""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager


def init_config_manager(config_path: Optional[str] = None) -> ConfigManager:
    """初始化配置管理器"""
    global _config_manager
    _config_manager = ConfigManager(config_path)
    return _config_manager


def _find_config_file() -> Optional[Path]:
    """查找配置文件（按优先级顺序）

    搜索顺序：
    1. ~/.clude/.clude.yaml   （主配置位置）
    2. ~/.clude/.clude.yml
    3. ./.clude/.clude.yaml   （工作区级覆盖/兼容）
    4. ./.clude/.clude.yml
    5. ./clude.yaml (向后兼容)
    6. ./clude.yml (向后兼容)

    Returns:
        配置文件路径，如果找到的话
    """
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


def _load_yaml_config(config_path: Path) -> Dict[str, Any]:
    """从YAML文件加载配置

    Args:
        config_path: 配置文件路径

    Returns:
        配置字典
    """
    if not YAML_AVAILABLE:
        raise ImportError("PyYAML is not installed. Install with: pip install PyYAML")

    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f) or {}


def _load_config_from_file() -> Dict[str, Any]:
    """从文件加载配置（如果存在的话）

    Returns:
        从文件加载的配置字典
    """
    config_file = _find_config_file()
    if config_file:
        try:
            return _load_yaml_config(config_file)
        except Exception as e:
            # 如果加载失败，返回空字典，使用默认配置；同时给出可观测的告警
            print(f"警告：加载配置文件失败（{config_file}），将使用默认配置: {e}")

    return {}


def _order_top_level_keys_for_yaml(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    将顶层 key 按 .clude/.clude.example.yaml 的顺序输出，保证配置文件可读性与一致性。
    未在顺序表里的 key 会按原有顺序追加到末尾。
    """
    preferred_order = [
        # 额外字段：如果存在，放到最前（示例文件未包含，但项目配置包含）
        "workspace_root",
        # 与示例文件一致的顺序
        "llm",
        "policy",
        "limits",
        "logging",
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


def _get_repo_root() -> Optional[Path]:
    """尽量定位仓库根目录（用于读取 .clude/.clude.example.yaml 模板）。"""
    try:
        # .../src/clude_code/config/config.py -> parents: config, clude_code, src, repo_root
        return Path(__file__).resolve().parents[3]
    except Exception:
        return None


def _yaml_inline_scalar(value: Any) -> str:
    """将 Python 值渲染为单行 YAML scalar/flow 值。"""
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


def _split_value_and_comment(rest: str) -> tuple[str, str]:
    """
    将 `: xxx  # comment` 分成 value 与 comment（保留 # 及其后内容）。
    简化实现：以第一个 `#` 作为注释起点（适用于我们的示例模板）。
    """
    if "#" not in rest:
        return rest.rstrip(), ""
    idx = rest.find("#")
    return rest[:idx].rstrip(), rest[idx:].rstrip()


def _render_commented_yaml(data: Dict[str, Any]) -> str:
    """
    生成带中文注释的 YAML 配置文本。
    策略：以 `.clude/.clude.example.yaml` 为模板，按 key 路径替换值，保留原注释与顺序。
    """
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


