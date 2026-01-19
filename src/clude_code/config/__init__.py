"""
配置模块统一管理

本目录包含项目的所有配置文件：
- config.py: 主配置文件类和默认配置
- tools_config.py: 工具模块专用配置

统一导入接口：
    from clude_code.config import CludeConfig, get_file_config, set_tool_configs
"""

# 导出主要配置类和函数
from .config import (
    # 基础配置类
    LLMConfig,
    PolicyConfig,
    LimitsConfig,
    LoggingConfig,
    OrchestratorConfig,
    RAGConfig,
    # UI和扩展配置
    UIConfig,
    EditorConfig,
    HistoryConfig,
    # 主配置类（必须在ExtendedCludeConfig之前）
    CludeConfig,
    ExtendedCludeConfig,
    ConfigManager,
    get_config_manager,
    init_config_manager,
)

# 导出配置向导
from .config_wizard import ConfigWizard, run_config_wizard

from .tools_config import (
    # 配置类
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
    ToolConfigs,
    # 便捷函数
    set_tool_configs,
    get_tool_configs,
    get_weather_config,
    get_file_config,
    get_directory_config,
    get_command_config,
    get_search_config,
    get_web_config,
    get_patch_config,
    get_display_config,
    get_question_config,
    get_repo_map_config,
    get_skill_config,
    get_task_config,
)

__all__ = [
    # 主配置
    "CludeConfig",
    "LLMConfig",
    "PolicyConfig",
    "LimitsConfig",
    "LoggingConfig",
    "OrchestratorConfig",
    "RAGConfig",
    # 工具配置
    "WeatherToolConfig",
    "FileToolConfig",
    "DirectoryToolConfig",
    "CommandToolConfig",
    "SearchToolConfig",
    "WebToolConfig",
    "PatchToolConfig",
    "DisplayToolConfig",
    "QuestionToolConfig",
    "RepoMapToolConfig",
    "SkillToolConfig",
    "TaskToolConfig",
    "ToolConfigs",
    # 工具配置函数
    "set_tool_configs",
    "get_tool_configs",
    "get_weather_config",
    "get_file_config",
    "get_directory_config",
    "get_command_config",
    "get_search_config",
    "get_web_config",
    "get_patch_config",
    "get_display_config",
    "get_question_config",
    "get_repo_map_config",
    "get_skill_config",
    "get_task_config",
]
