"""
配置管理器 - CLI接口

提供CLI命令行接口来管理配置。
主要功能已移动到 src/clude_code/config/config.py

此文件保留向后兼容性，确保现有的CLI命令仍然工作。
"""

# 导入已移动的类和函数以保持向后兼容性
from clude_code.config import (
    UIConfig,
    EditorConfig,
    HistoryConfig,
    ExtendedCludeConfig,
    ConfigManager,
    get_config_manager,
    init_config_manager,
)