"""
CLI 日志管理模块
统一管理所有 CLI 相关的日志输出
"""
import logging
from typing import Optional

from clude_code.config import CludeConfig
from clude_code.observability.logger import get_logger


class CLILogger:
    """CLI 日志管理器，统一处理所有 CLI 相关的日志"""

    def __init__(self):
        self._console_logger: Optional[logging.Logger] = None
        self._file_logger: Optional[logging.Logger] = None
        self._cfg: Optional[CludeConfig] = None

    def _ensure_initialized(self):
        """确保日志记录器已初始化"""
        if self._cfg is None:
            self._cfg = CludeConfig()

        if self._console_logger is None:
            self._console_logger = get_logger(
                "cli.console",
                workspace_root=self._cfg.workspace_root,
                log_to_console=self._cfg.logging.log_to_console,
            )

        if self._file_logger is None:
            self._file_logger = get_logger(
                "cli.flow",
                workspace_root=self._cfg.workspace_root,
                log_to_console=False,  # 文件日志不输出到控制台
            )

    @property
    def console(self) -> logging.Logger:
        """获取控制台日志记录器（支持控制台输出）"""
        self._ensure_initialized()
        return self._console_logger

    @property
    def file(self) -> logging.Logger:
        """获取文件日志记录器（仅写入文件）"""
        self._ensure_initialized()
        return self._file_logger

    def debug(self, msg: str, *args, **kwargs):
        """DEBUG 级别日志"""
        self.console.debug(msg, *args, **kwargs)

    def info(self, msg: str, *args, **kwargs):
        """INFO 级别日志"""
        self.console.info(msg, *args, **kwargs)

    def warning(self, msg: str, *args, **kwargs):
        """WARNING 级别日志"""
        self.console.warning(msg, *args, **kwargs)

    def error(self, msg: str, *args, **kwargs):
        """ERROR 级别日志"""
        self.console.error(msg, *args, **kwargs)

    def critical(self, msg: str, *args, **kwargs):
        """CRITICAL 级别日志"""
        self.console.critical(msg, *args, **kwargs)

    def exception(self, msg: str, *args, exc_info=True, **kwargs):
        """记录异常信息"""
        self.console.error(msg, *args, exc_info=exc_info, **kwargs)

    # 文件专用日志方法
    def log_turn_start(self, user_text: str, debug: bool, live: bool):
        """记录对话开始"""
        self.file.info(
            f"Turn Start - input: {user_text[:100]}..., debug={debug}, live={live}, "
            f"model={self._cfg.llm.model if self._cfg else 'unknown'}"
        )

    def log_turn_end(self, trace_id: str, tool_used: bool, events_count: int):
        """记录对话结束"""
        self.file.info(
            f"Turn End - trace_id={trace_id}, tool_used={tool_used}, events={events_count}"
        )

    def log_debug_trace(self, turn_events: list):
        """记录调试轨迹"""
        self.console.debug("--- agent 执行轨迹 ---")
        for event in turn_events:
            step = event.get("step", "?")
            ev = event.get("event", "")
            data = event.get("data", {})

            if ev in {"llm_response", "final_text"}:
                txt = str(data.get("text", ""))
                self.console.debug(f"{step}. {ev} {txt[:120]}...")
            elif ev == "tool_call_parsed":
                self.console.debug(f"{step}. tool {data.get('tool', '')} args={data.get('args', {})}")
            else:
                self.console.debug(f"{step}. {ev}")


# 全局 CLI 日志实例
_cli_logger: Optional[CLILogger] = None

def get_cli_logger() -> CLILogger:
    """获取全局 CLI 日志管理器"""
    global _cli_logger
    if _cli_logger is None:
        _cli_logger = CLILogger()
    return _cli_logger


# 便捷函数（向后兼容）
def get_console_logger() -> logging.Logger:
    """获取控制台日志记录器（向后兼容）"""
    return get_cli_logger().console

def get_file_logger() -> logging.Logger:
    """获取文件日志记录器（向后兼容）"""
    return get_cli_logger().file