"""
工具模块日志辅助函数（Tool Logger Helper）

为所有工具模块提供统一的日志初始化功能，参考天气模块的实现。

使用方式：
    from clude_code.tooling.logger_helper import get_tool_logger
    
    _logger = get_tool_logger(__name__)
    _logger.info("工具执行开始")
"""
from __future__ import annotations

import logging
from typing import Any

from clude_code.observability.logger import get_logger
from clude_code.config.config import LoggingConfig


# 全局 logger 缓存（模块名 -> Logger）
_logger_cache: dict[str, logging.Logger] = {}


def get_tool_logger(
    module_name: str,
    log_to_file: bool = True,
    cfg: Any | None = None,
) -> logging.Logger:
    """
    获取工具模块的 logger（延迟初始化，统一配置）。
    
    所有工具模块应使用此函数创建 logger，确保：
    1. 统一的日志格式和配置
    2. 支持控制是否写入文件
    3. 自动从全局配置获取日志设置
    
    Args:
        module_name: 模块名（通常是 __name__）
        log_to_file: 是否写入文件（默认 True）
        cfg: CludeConfig 对象（可选，用于获取 workspace_root 和日志配置）
    
    Returns:
        已配置的 Logger 实例
    
    Example:
        ```python
        from clude_code.tooling.logger_helper import get_tool_logger
        
        _logger = get_tool_logger(__name__)
        _logger.info("工具执行开始")
        ```
    """
    global _logger_cache
    
    # 如果已缓存，直接返回
    if module_name in _logger_cache:
        return _logger_cache[module_name]
    
    # 确定 workspace_root
    workspace_root = "."
    if cfg is not None:
        if hasattr(cfg, "workspace_root"):
            workspace_root = cfg.workspace_root
    
    # 确定日志配置
    if cfg is not None and hasattr(cfg, "logging"):
        logging_cfg = cfg.logging
    else:
        logging_cfg = LoggingConfig()
    
    # 确定是否写入文件
    if not log_to_file:
        workspace_root = None
    
    # 创建并配置 logger
    logger_file_path = None
    if log_to_file and hasattr(logging_cfg, "file_path") and logging_cfg.file_path:
        logger_file_path = logging_cfg.file_path
    
    logger = get_logger(
        module_name,
        workspace_root=workspace_root,
        log_file=logger_file_path,
        log_to_console=logging_cfg.log_to_console,
        level=logging_cfg.level,
        log_format=logging_cfg.log_format,
        date_format=logging_cfg.date_format,
    )
    
    # 缓存 logger
    _logger_cache[module_name] = logger
    
    return logger


def init_tool_logger_from_config(module_name: str, cfg: Any) -> logging.Logger:
    """
    从配置初始化工具 logger（用于工具配置注入时调用）。

    Args:
        module_name: 模块名（通常是 __name__）
        cfg: CludeConfig 对象

    Returns:
        已配置的 Logger 实例
    """
    # 从工具配置中获取 log_to_file 设置
    log_to_file = True
    try:
        from clude_code.config import get_tool_configs
        tool_configs = get_tool_configs()

        # 根据模块名确定配置
        if "weather" in module_name:
            log_to_file = tool_configs.weather.log_to_file
        elif "read_file" in module_name or "write_file" in module_name:
            log_to_file = tool_configs.file.log_to_file
        elif "list_dir" in module_name or "glob_search" in module_name:
            log_to_file = tool_configs.directory.log_to_file
        elif "run_cmd" in module_name:
            log_to_file = tool_configs.command.log_to_file
        elif "grep" in module_name or "search" in module_name:
            log_to_file = tool_configs.search.log_to_file
        elif "webfetch" in module_name:
            log_to_file = tool_configs.web.log_to_file
        elif "patching" in module_name:
            log_to_file = tool_configs.patch.log_to_file
        elif "display" in module_name:
            log_to_file = tool_configs.display.log_to_file
        elif "question" in module_name:
            log_to_file = tool_configs.question.log_to_file
        elif "repo_map" in module_name:
            log_to_file = tool_configs.repo_map.log_to_file
        elif "skill" in module_name:
            log_to_file = tool_configs.skill.log_to_file
        elif "task_agent" in module_name or "todo_manager" in module_name:
            log_to_file = tool_configs.task.log_to_file
    except Exception:
        # 如果获取配置失败，使用默认值
        pass

    return get_tool_logger(module_name, log_to_file=log_to_file, cfg=cfg)

