"""
统一日志系统模块。

提供带文件名和行号的日志输出，格式：`[文件名:行号] 日志内容`
支持 Rich markup（颜色、样式等）。
"""
import inspect
import logging
import os
import sys
from pathlib import Path
from typing import Optional, Union
from logging.handlers import RotatingFileHandler

from rich.console import Console
from rich.logging import RichHandler

"""
自定义 Rich 处理器，在日志开头添加文件名和行号。

格式：级别     [文件名:行号] 级别 - 消息内容（支持 Rich markup）
"""
class FileLineRichHandler(RichHandler):

    
    def emit(self, record: logging.LogRecord) -> None:
        # 获取调用日志的文件名和行号
        # logging 的 findCaller 会自动跳过日志框架本身
        try:
            # 使用 logging 的内置机制查找调用者（跳过日志框架）
            fn, lno, func, sinfo = self.findCaller(record, stack_info=False)
            if fn:
                record.filename = Path(fn).name
                record.lineno_caller = lno
            else:
                # 如果找不到，使用 logging 记录的信息
                record.filename = Path(record.pathname).name
                record.lineno_caller = record.lineno
        except Exception:
            # 如果出错，使用默认值
            record.filename = Path(record.pathname).name
            record.lineno_caller = record.lineno
        
        # 调用父类方法
        super().emit(record)
    """
    重写 render 方法，控制台输出只显示消息内容（不带前缀）。
    文件输出会在 FileLineFileHandler 中添加完整格式。
    """
    def render(self, *, record: logging.LogRecord, traceback, message_renderable, **kwargs):

        # 控制台输出直接使用原始消息，不添加前缀
        # 调用父类 render
        return super().render(
            record=record,
            traceback=traceback,
            message_renderable=message_renderable,
            **kwargs
        )


class FileLineFileHandler(RotatingFileHandler):
    """
    文件输出处理器，支持自动滚动，格式与控制台一致。
    
    格式：级别     [文件名:行号] 级别 - 消息内容
    """
    
    def __init__(
        self, 
        filename: str, 
        mode: str = "a", 
        encoding: str = "utf-8", 
        delay: bool = False,
        maxBytes: int = 10_485_760,  # 10MB
        backupCount: int = 5,
        log_format: Optional[str] = None,
        date_format: Optional[str] = None
    ):
        super().__init__(filename, mode, maxBytes, backupCount, encoding, delay)
        # 设置格式化器
        fmt = log_format or "%(levelname)-8s [%(filename)s:%(lineno_caller)s] %(levelname)s - %(message)s"
        datefmt = date_format or ""
        
        formatter = logging.Formatter(fmt=fmt, datefmt=datefmt)
        self.setFormatter(formatter)
    
    def emit(self, record: logging.LogRecord) -> None:
        # 获取调用日志的文件名和行号
        try:
            # 使用 logging 的内置机制查找调用者（跳过日志框架）
            fn, lno, func, sinfo = self.findCaller(record, stack_info=False)
            if fn:
                record.filename = Path(fn).name
                record.lineno_caller = lno
            else:
                # 如果找不到，使用 logging 记录的信息
                record.filename = Path(record.pathname).name
                record.lineno_caller = record.lineno
        except Exception:
            # 如果出错，使用默认值
            record.filename = Path(record.pathname).name
            record.lineno_caller = record.lineno
        
        # 调用父类方法
        super().emit(record)

"""
获取配置好的日志记录器。

参数:
    name: 日志记录器名称（通常是模块名，如 __name__）
    level: 日志级别（可以是 int 如 logging.INFO，也可以是字符串如 'DEBUG'）
    log_file: 可选的文件路径，如果提供则同时输出到文件
    workspace_root: 工作区根目录，如果提供且 log_file 未指定，则自动创建 .clude/logs/app.log
    log_to_console: 是否输出到控制台（默认 False，只写入文件）
    max_bytes: 日志文件最大字节数
    backup_count: 保留的日志备份数量
    log_format: 自定义日志格式
    date_format: 自定义日期格式

返回:
    配置好的 Logger 实例
"""
def get_logger(
    name: str,
    level: Union[int, str] = logging.INFO,
    log_file: Optional[str] = None,
    workspace_root: Optional[str] = None,
    log_to_console: bool = False,
    max_bytes: int = 10_485_760,
    backup_count: int = 5,
    log_format: Optional[str] = None,
    date_format: Optional[str] = None,
    project_id: Optional[str] = None,
) -> logging.Logger:

    logger = logging.getLogger(name)
    
    # 处理字符串级别的转换
    if isinstance(level, str):
        level = getattr(logging, level.upper(), logging.INFO)
    
    logger.setLevel(level)
    
    # 检查是否已有控制台处理器
    has_console_handler = any(
        isinstance(h, FileLineRichHandler) for h in logger.handlers
    )
    
    # 检查是否已有文件处理器
    has_file_handler = any(
        isinstance(h, FileLineFileHandler) for h in logger.handlers
    )
    
    # 根据配置决定是否添加控制台处理器
    if log_to_console:
        if not has_console_handler:
            # 创建 Rich 控制台处理器（支持颜色和格式化）
            console = Console(stderr=True, force_terminal=True)  # force_terminal 确保颜色显示
            console_handler = FileLineRichHandler(
                console=console,
                show_time=False,  # 不显示时间
                show_path=False,  # 不显示路径
                rich_tracebacks=True,
                markup=True,  # 支持 Rich markup（颜色、样式）
                show_level=False,  # 不显示级别，只显示消息内容
            )
            
            # 设置格式化器（只格式化级别，消息由 Rich 处理）
            formatter = logging.Formatter(
                fmt="%(message)s",  # Rich 会处理格式和颜色，这里只传递消息
                datefmt="",
            )
            console_handler.setFormatter(formatter)
            
            logger.addHandler(console_handler)
    else:
        # 核心修复点：如果不输出到控制台，则禁止消息向上传递给带有控制台处理器的父 logger
        logger.propagate = False

    # 先确定日志文件路径，再做创建/exists 检查（避免 log_file=None 崩溃）
    effective_log_file = log_file
    if workspace_root:
        try:
            from clude_code.core.project_paths import resolve_path_template, ProjectPaths
            if effective_log_file:
                effective_log_file = resolve_path_template(
                    effective_log_file,
                    workspace_root=workspace_root,
                    project_id=project_id,
                )
            else:
                paths = ProjectPaths(workspace_root, project_id, auto_create=True)
                effective_log_file = str(paths.app_log_file())
        except Exception:
            # 兜底：旧逻辑
            if not effective_log_file:
                log_dir = Path(workspace_root) / ".clude" / "logs"
                log_dir.mkdir(parents=True, exist_ok=True)
                effective_log_file = str(log_dir / "app.log")

    # 如果指定了日志文件，确保目录存在并添加文件处理器
    if effective_log_file:
        try:
            os.makedirs(os.path.dirname(effective_log_file), exist_ok=True)
        except Exception:
            # 兜底：目录创建失败不阻塞控制台日志
            effective_log_file = None

    if effective_log_file and not has_file_handler:
        file_handler = FileLineFileHandler(
            effective_log_file,
            encoding="utf-8",
            maxBytes=max_bytes,
            backupCount=backup_count,
            log_format=log_format,
            date_format=date_format
        )
        file_handler.setLevel(level)
        logger.addHandler(file_handler)
    
    return logger


# 全局默认日志记录器（用于快速使用）
_default_logger: Optional[logging.Logger] = None

"""
获取默认日志记录器（单例模式）。

返回:
    全局默认 Logger 实例
"""
def get_default_logger() -> logging.Logger:

    global _default_logger
    if _default_logger is None:
        _default_logger = get_logger("clude_code")
    return _default_logger

"""
DEBUG 级别日志快捷函数。
"""
def debug(msg: str, *args, **kwargs) -> None:
    
    get_default_logger().debug(msg, *args, **kwargs)

"""
INFO 级别日志快捷函数。
"""
def info(msg: str, *args, **kwargs) -> None:
    get_default_logger().info(msg, *args, **kwargs)

"""
WARNING 级别日志快捷函数。
"""
def warning(msg: str, *args, **kwargs) -> None:
    get_default_logger().warning(msg, *args, **kwargs)

"""
ERROR 级别日志快捷函数。
"""
def error(msg: str, *args, **kwargs) -> None:

    get_default_logger().error(msg, *args, **kwargs)

"""
ERROR 级别日志快捷函数（带异常信息）。
"""
def exception(msg: str, *args, exc_info=True, **kwargs) -> None:
    get_default_logger().error(msg, *args, exc_info=exc_info, **kwargs)

