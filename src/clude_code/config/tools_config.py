"""
工具模块统一配置管理（Tool Configuration Management）

本模块集中管理所有工具模块的配置，遵循项目代码规范：
- 配置集中化：所有工具配置统一在此模块定义
- 配置优先级：环境变量 > 配置文件 > 代码默认值
- 配置注入：通过 set_tool_config() 统一注入

符合规范：docs/CODE_SPECIFICATION.md 3.1 模块配置统一管理
"""
from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class WeatherToolConfig(BaseModel):
    """
    天气工具配置（OpenWeatherMap）

    获取免费 API Key: https://openweathermap.org/api
    """
    enabled: bool = Field(default=True, description="是否启用天气工具。")
    api_key: str = Field(
        default="",
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
    base_url: str = Field(
        default="https://api.openweathermap.org/data/2.5",
        description="OpenWeatherMap API Base URL（默认 https://api.openweathermap.org/data/2.5）。"
    )
    geo_url: str = Field(
        default="https://api.openweathermap.org/geo/1.0",
        description="OpenWeatherMap Geo API Base URL（默认 https://api.openweathermap.org/geo/1.0）。"
    )
    api_key_env_name: str = Field(
        default="OPENWEATHERMAP_API_KEY",
        description="天气 API Key 的环境变量名（默认 OPENWEATHERMAP_API_KEY）。"
    )


class FileToolConfig(BaseModel):
    """文件操作工具配置（read_file, write_file）"""
    enabled: bool = Field(default=True, description="是否启用文件操作工具。")
    log_to_file: bool = Field(
        default=True,
        description="是否将文件操作日志写入文件。默认 True，写入 .clude/logs/app.log。"
    )


class DirectoryToolConfig(BaseModel):
    """目录操作工具配置（list_dir, glob_search）"""
    enabled: bool = Field(default=True, description="是否启用目录操作工具。")
    log_to_file: bool = Field(
        default=True,
        description="是否将目录操作日志写入文件。默认 True，写入 .clude/logs/app.log。"
    )
    ignore_dirs: list[str] = Field(
        default_factory=lambda: [".git", ".clude", "node_modules", ".venv", "dist", "build"],
        description="目录/文件遍历时默认忽略的目录名（降低噪音与提升性能）。"
    )


class CommandToolConfig(BaseModel):
    """命令执行工具配置（run_cmd）"""
    enabled: bool = Field(default=True, description="是否启用命令执行工具。")
    timeout_s: int = Field(
        default=30,
        ge=1,
        le=300,
        description="命令执行超时时间（秒）。"
    )
    log_to_file: bool = Field(
        default=True,
        description="是否将命令执行日志写入文件。默认 True，写入 .clude/logs/app.log。"
    )



"""
搜索工具配置（grep, search）
"""
class SearchToolConfig(BaseModel):
    enabled: bool = Field(default=True, description="是否启用搜索工具。")
    websearch_providers: list[str] = Field(
        default_factory=lambda: ["open_websearch_mcp", "serper"],
        description="网页搜索资料来源优先级（默认优先 Open-WebSearch MCP，失败回退 Serper）。",
    )
    open_websearch_mcp_enabled: bool = Field(
        default=True,
        description="是否启用 Open-WebSearch MCP 搜索源（推荐默认开启，优先使用）。",
    )
    open_websearch_mcp_base_url: str = Field(
        default="http://127.0.0.1:8765",
        description="Open-WebSearch MCP 服务地址（HTTP）。示例：http://127.0.0.1:8765",
    )
    open_websearch_mcp_endpoint: str = Field(
        default="/search",
        description="Open-WebSearch MCP 搜索接口路径（与 base_url 拼接）。默认 /search。",
    )
    open_websearch_mcp_api_key: str = Field(
        default="",
        description="Open-WebSearch MCP API Key（如服务需要）。建议用环境变量 CLUDE_SEARCH__OPEN_WEBSEARCH_MCP_API_KEY。",
    )
    serper_api_key: str = Field(
        default="",
        description="Serper API Key（免费额度：2500次/月）。建议用环境变量 CLUDE_SEARCH__SERPER_API_KEY 设置。"
    )
    serper_gl: str = Field(default="cn", description="Serper 地域参数 gl（默认 cn）。")
    serper_hl: str = Field(default="zh-cn", description="Serper 语言参数 hl（默认 zh-cn）。")

    # codesearch（代码搜索）：本项目仅实现网络搜索（Grep.app）
    grep_app_enabled: bool = Field(
        default=True,
        description="是否启用 Grep.app 代码搜索源。",
    )
    grep_app_base_url: str = Field(
        default="https://grep.app",
        description="Grep.app 服务地址（默认 https://grep.app）。",
    )
    grep_app_endpoint: str = Field(
        default="/api/search",
        description="Grep.app 搜索 API 路径（默认 /api/search）。",
    )
    timeout_s: int = Field(
        default=30,
        ge=1,
        le=300,
        description="搜索超时时间（秒）。"
    )
    max_results: int = Field(
        default=1000,
        ge=1,
        le=10000,
        description="搜索最大结果数量。"
    )
    log_to_file: bool = Field(
        default=True,
        description="是否将搜索日志写入文件。默认 True，写入 .clude/logs/app.log。"
    )
    # grep（本地代码搜索）配置：目录过滤、语言后缀映射、Python 扫描文件上限
    grep_ignore_dirs: list[str] = Field(
        default_factory=lambda: [".git", ".clude", "node_modules", ".venv", "dist", "build"],
        description="grep 搜索时默认忽略的目录名（降低噪音与提升性能）。"
    )
    grep_language_extensions: dict[str, list[str]] = Field(
        default_factory=lambda: {
            "c": [".c", ".h"],
            "cpp": [".cpp", ".cc", ".cxx", ".h", ".hpp", ".hh"],
            "java": [".java"],
            "python": [".py"],
            "js": [".js", ".jsx", ".ts", ".tsx"],
            "go": [".go"],
            "rust": [".rs"],
        },
        description="grep 的 language->扩展名映射（用于 language 过滤：如 cpp/python）。",
    )
    grep_python_max_file_bytes: int = Field(
        default=2_000_000,
        ge=0,
        le=100_000_000,
        description="当缺少 rg 时，Python 扫描单文件最大字节数（0=不限制）。默认 2,000,000（约 2MB）。"
    )


class WebToolConfig(BaseModel):
    """网络工具配置（webfetch, search）"""
    enabled: bool = Field(default=True, description="是否启用网络工具。")
    timeout_s: int = Field(
        default=30,
        ge=1,
        le=300,
        description="网络请求超时时间（秒）。"
    )
    max_content_length: int = Field(
        default=1000000,
        ge=1000,
        le=1000000,
        description="最大内容长度（字符）。"
    )
    log_to_file: bool = Field(
        default=True,
        description="是否将网络工具日志写入文件。默认 True，写入 .clude/logs/app.log。"
    )
    # webfetch 缓存配置
    cache_enabled: bool = Field(
        default=True,
        description="是否启用 webfetch 本地 Markdown 缓存。"
    )
    cache_dir: str = Field(
        default=".clude/markdown",
        description="webfetch 缓存目录（相对于 workspace_root）。"
    )
    cache_expiry_days: int = Field(
        default=7,
        ge=1,
        le=365,
        description="缓存有效期（天）。默认 7 天。"
    )
    cache_max_filename_length: int = Field(
        default=100,
        ge=16,
        le=255,
        description="webfetch 缓存文件名最大长度（不含扩展名）。默认 100。"
    )
    cache_index_enabled: bool = Field(
        default=True,
        description="是否启用 webfetch 缓存索引文件（加速命中）。"
    )
    cache_index_filename: str = Field(
        default=".cache_index",
        description="webfetch 缓存索引文件名（位于 cache_dir 内）。"
    )
    cache_scan_prefix_bytes: int = Field(
        default=2000,
        ge=256,
        le=20000,
        description="遍历缓存目录时每个文件最多读取的前缀字节数（用于解析 YAML 头部）。"
    )
    cache_max_collision_attempts: int = Field(
        default=100,
        ge=1,
        le=1000,
        description="缓存落盘时处理文件名冲突的最大尝试次数。超过则放弃写缓存。"
    )


class PatchToolConfig(BaseModel):
    """补丁工具配置（patching）"""
    enabled: bool = Field(default=True, description="是否启用补丁工具。")
    log_to_file: bool = Field(
        default=True,
        description="是否将补丁操作日志写入文件。默认 True，写入 .clude/logs/app.log。"
    )


class DisplayToolConfig(BaseModel):
    """显示工具配置（display）"""
    enabled: bool = Field(default=True, description="是否启用显示工具。")
    max_content_length: int = Field(
        default=10000,
        ge=100,
        le=100000,
        description="显示内容最大长度（字符）。"
    )
    log_to_file: bool = Field(
        default=True,
        description="是否将显示日志写入文件。默认 True，写入 .clude/logs/app.log。"
    )


class QuestionToolConfig(BaseModel):
    """提问工具配置（question）"""
    enabled: bool = Field(default=True, description="是否启用提问工具。")
    log_to_file: bool = Field(
        default=True,
        description="是否将提问日志写入文件。默认 True，写入 .clude/logs/app.log。"
    )


class RepoMapToolConfig(BaseModel):
    """仓库地图工具配置（repo_map）"""
    enabled: bool = Field(default=True, description="是否启用仓库地图工具。")
    log_to_file: bool = Field(
        default=True,
        description="是否将仓库地图日志写入文件。默认 True，写入 .clude/logs/app.log。"
    )


class SkillToolConfig(BaseModel):
    """技能工具配置（skill）"""
    enabled: bool = Field(default=True, description="是否启用技能工具。")
    log_to_file: bool = Field(
        default=True,
        description="是否将技能加载日志写入文件。默认 True，写入 .clude/logs/app.log。"
    )


class TaskToolConfig(BaseModel):
    """任务工具配置（task_agent, todo_manager）"""
    enabled: bool = Field(default=True, description="是否启用任务工具。")
    log_to_file: bool = Field(
        default=True,
        description="是否将任务操作日志写入文件。默认 True，写入 .clude/logs/app.log。"
    )
 
class ToolConfigs(BaseModel):
    """
    所有工具模块的配置集合

    新增工具配置时，在此类中添加对应的配置字段。
    """
    # 天气工具
    weather: WeatherToolConfig = Field(default_factory=WeatherToolConfig)

    # 文件操作工具
    file: FileToolConfig = Field(default_factory=FileToolConfig)

    # 目录操作工具
    directory: DirectoryToolConfig = Field(default_factory=DirectoryToolConfig)

    # 命令执行工具
    command: CommandToolConfig = Field(default_factory=CommandToolConfig)

    # 搜索工具
    search: SearchToolConfig = Field(default_factory=SearchToolConfig)

    # 网络工具
    web: WebToolConfig = Field(default_factory=WebToolConfig)

    # 补丁工具
    patch: PatchToolConfig = Field(default_factory=PatchToolConfig)

    # 显示工具
    display: DisplayToolConfig = Field(default_factory=DisplayToolConfig)

    # 提问工具
    question: QuestionToolConfig = Field(default_factory=QuestionToolConfig)

    # 仓库地图工具
    repo_map: RepoMapToolConfig = Field(default_factory=RepoMapToolConfig)

    # 技能工具
    skill: SkillToolConfig = Field(default_factory=SkillToolConfig)

    # 任务工具
    task: TaskToolConfig = Field(default_factory=TaskToolConfig)


# 全局工具配置缓存（由 AgentLoop 初始化时注入）
_tool_configs: ToolConfigs | None = None


def set_tool_configs(cfg: Any) -> None:
    """
    设置工具配置（由 AgentLoop 在初始化时调用）

    从 CludeConfig 中提取工具相关配置并缓存。

    Args:
        cfg: CludeConfig 对象
    """
    global _tool_configs

    # 从 CludeConfig 提取所有工具配置
    _tool_configs = ToolConfigs(
        # 天气工具配置
        weather=WeatherToolConfig(
            enabled=getattr(cfg.weather, "enabled", True),
            api_key=getattr(cfg.weather, "api_key", ""),
            default_units=getattr(cfg.weather, "default_units", "metric"),
            default_lang=getattr(cfg.weather, "default_lang", "zh_cn"),
            timeout_s=getattr(cfg.weather, "timeout_s", 10),
            cache_ttl_s=getattr(cfg.weather, "cache_ttl_s", 300),
            log_to_file=getattr(cfg.weather, "log_to_file", True),
            base_url=getattr(cfg.weather, "base_url", "https://api.openweathermap.org/data/2.5"),
            geo_url=getattr(cfg.weather, "geo_url", "https://api.openweathermap.org/geo/1.0"),
            api_key_env_name=getattr(cfg.weather, "api_key_env_name", "OPENWEATHERMAP_API_KEY"),
        ),
        # 文件工具配置
        file=FileToolConfig(
            enabled=getattr(cfg.file, "enabled", True),
            log_to_file=getattr(cfg.file, "log_to_file", True),
        ),
        # 目录工具配置
        directory=DirectoryToolConfig(
            enabled=getattr(cfg.directory, "enabled", True),
            log_to_file=getattr(cfg.directory, "log_to_file", True),
            ignore_dirs=getattr(cfg.directory, "ignore_dirs", [".git", ".clude", "node_modules", ".venv", "dist", "build"]),
        ),
        # 命令工具配置
        command=CommandToolConfig(
            enabled=getattr(cfg.command, "enabled", True),
            timeout_s=getattr(cfg.command, "timeout_s", 30),
            log_to_file=getattr(cfg.command, "log_to_file", True),
        ),
        # 搜索工具配置
        search=SearchToolConfig(
            enabled=getattr(cfg.search, "enabled", True),
            websearch_providers=getattr(cfg.search, "websearch_providers", ["open_websearch_mcp", "serper"]),
            open_websearch_mcp_enabled=getattr(cfg.search, "open_websearch_mcp_enabled", True),
            open_websearch_mcp_base_url=getattr(cfg.search, "open_websearch_mcp_base_url", "http://127.0.0.1:8765"),
            open_websearch_mcp_endpoint=getattr(cfg.search, "open_websearch_mcp_endpoint", "/search"),
            open_websearch_mcp_api_key=getattr(cfg.search, "open_websearch_mcp_api_key", ""),
            serper_api_key=getattr(cfg.search, "serper_api_key", ""),
            serper_gl=getattr(cfg.search, "serper_gl", "cn"),
            serper_hl=getattr(cfg.search, "serper_hl", "zh-cn"),
            grep_app_enabled=getattr(cfg.search, "grep_app_enabled", True),
            grep_app_base_url=getattr(cfg.search, "grep_app_base_url", "https://grep.app"),
            grep_app_endpoint=getattr(cfg.search, "grep_app_endpoint", "/api/search"),
            timeout_s=getattr(cfg.search, "timeout_s", 30),
            max_results=getattr(cfg.search, "max_results", 1000),
            log_to_file=getattr(cfg.search, "log_to_file", True),
            grep_ignore_dirs=getattr(cfg.search, "grep_ignore_dirs", [".git", ".clude", "node_modules", ".venv", "dist", "build"]),
            grep_language_extensions=getattr(cfg.search, "grep_language_extensions", SearchToolConfig().grep_language_extensions),
            grep_python_max_file_bytes=getattr(cfg.search, "grep_python_max_file_bytes", 2_000_000),
        ),
        # 网络工具配置
        web=WebToolConfig(
            enabled=getattr(cfg.web, "enabled", True),
            timeout_s=getattr(cfg.web, "timeout_s", 30),
            max_content_length=getattr(cfg.web, "max_content_length", 50000),
            log_to_file=getattr(cfg.web, "log_to_file", True),
            cache_enabled=getattr(cfg.web, "cache_enabled", True),
            cache_dir=getattr(cfg.web, "cache_dir", ".clude/markdown"),
            cache_expiry_days=getattr(cfg.web, "cache_expiry_days", 7),
            cache_max_filename_length=getattr(cfg.web, "cache_max_filename_length", 100),
            cache_index_enabled=getattr(cfg.web, "cache_index_enabled", True),
            cache_index_filename=getattr(cfg.web, "cache_index_filename", ".cache_index"),
            cache_scan_prefix_bytes=getattr(cfg.web, "cache_scan_prefix_bytes", 2000),
            cache_max_collision_attempts=getattr(cfg.web, "cache_max_collision_attempts", 100),
        ),
        # 补丁工具配置
        patch=PatchToolConfig(
            enabled=getattr(cfg.patch, "enabled", True),
            log_to_file=getattr(cfg.patch, "log_to_file", True),
        ),
        # 显示工具配置
        display=DisplayToolConfig(
            enabled=getattr(cfg.display, "enabled", True),
            max_content_length=getattr(cfg.display, "max_content_length", 10000),
            log_to_file=getattr(cfg.display, "log_to_file", True),
        ),
        # 提问工具配置
        question=QuestionToolConfig(
            enabled=getattr(cfg.question, "enabled", True),
            log_to_file=getattr(cfg.question, "log_to_file", True),
        ),
        # 仓库地图工具配置
        repo_map=RepoMapToolConfig(
            enabled=getattr(cfg.repo_map, "enabled", True),
            log_to_file=getattr(cfg.repo_map, "log_to_file", True),
        ),
        # 技能工具配置
        skill=SkillToolConfig(
            enabled=getattr(cfg.skill, "enabled", True),
            log_to_file=getattr(cfg.skill, "log_to_file", True),
        ),
        # 任务工具配置
        task=TaskToolConfig(
            enabled=getattr(cfg.task, "enabled", True),
            log_to_file=getattr(cfg.task, "log_to_file", True),
        ),
    )


def get_tool_configs() -> ToolConfigs:
    """
    获取工具配置
    
    Returns:
        ToolConfigs 对象
    """
    global _tool_configs
    if _tool_configs is None:
        # 如果未初始化，使用默认配置
        _tool_configs = ToolConfigs()
    return _tool_configs


def get_weather_config() -> WeatherToolConfig:
    """
    获取天气工具配置（便捷方法）

    Returns:
        WeatherToolConfig 对象
    """
    return get_tool_configs().weather


def get_file_config() -> FileToolConfig:
    """获取文件工具配置（read_file, write_file）"""
    return get_tool_configs().file


def get_directory_config() -> DirectoryToolConfig:
    """获取目录工具配置（list_dir, glob_search）"""
    return get_tool_configs().directory


def get_command_config() -> CommandToolConfig:
    """获取命令工具配置（run_cmd）"""
    return get_tool_configs().command


def get_search_config() -> SearchToolConfig:
    """获取搜索工具配置（grep, search）"""
    return get_tool_configs().search


def get_web_config() -> WebToolConfig:
    """获取网络工具配置（webfetch, search）"""
    return get_tool_configs().web


def get_patch_config() -> PatchToolConfig:
    """获取补丁工具配置（patching）"""
    return get_tool_configs().patch


def get_display_config() -> DisplayToolConfig:
    """获取显示工具配置（display）"""
    return get_tool_configs().display


def get_question_config() -> QuestionToolConfig:
    """获取提问工具配置（question）"""
    return get_tool_configs().question


def get_repo_map_config() -> RepoMapToolConfig:
    """获取仓库地图工具配置（repo_map）"""
    return get_tool_configs().repo_map


def get_skill_config() -> SkillToolConfig:
    """获取技能工具配置（skill）"""
    return get_tool_configs().skill


def get_task_config() -> TaskToolConfig:
    """获取任务工具配置（task_agent, todo_manager）"""
    return get_tool_configs().task

