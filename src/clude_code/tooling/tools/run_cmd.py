from __future__ import annotations

import os
import platform
import shlex
import subprocess
from pathlib import Path

from ..types import ToolResult
from ..workspace import resolve_in_workspace
from ..logger_helper import get_tool_logger
from ...config.tools_config import get_command_config

# 工具模块 logger（延迟初始化）
_logger = get_tool_logger(__name__)

# Shell 特性字符集（需要 shell=True 才能正确执行）
_SHELL_CHARS = {'|', '>', '<', '&', ';', '$', '`', '*', '?', '(', ')', '{', '}', '[', ']', '~'}


def _parse_command(command: str) -> tuple[list[str] | str, bool]:
    """
    智能解析命令，决定是否需要 shell 模式。
    
    安全优化（Phase 3）：
    - 不含 shell 特性时使用 shell=False（更安全）
    - 含 shell 特性时使用 shell=True（必须）
    
    Args:
        command: 命令字符串
    
    Returns:
        (args, use_shell): args 是参数列表或命令字符串，use_shell 是否使用 shell
    """
    # 检测是否包含 shell 特性
    needs_shell = any(c in command for c in _SHELL_CHARS)
    
    # 检测是否包含 shell 扩展语法
    if '$((' in command or '${' in command or '||' in command or '&&' in command:
        needs_shell = True
    
    if needs_shell:
        _logger.debug(f"[RunCmd] 检测到 shell 特性，使用 shell=True")
        return command, True
    
    # 尝试解析为参数列表
    try:
        if platform.system() == "Windows":
            # Windows 命令解析较复杂，对于简单命令尝试 split
            # 但如果命令包含引号则保留 shell 模式
            if '"' in command or "'" in command:
                return command, True
            args = command.split()
        else:
            # Unix 使用 shlex 进行安全解析
            args = shlex.split(command)
        
        if not args:
            return command, True
        
        _logger.debug(f"[RunCmd] 解析为参数列表，使用 shell=False")
        return args, False
    except ValueError as e:
        # 解析失败，回退到 shell 模式
        _logger.debug(f"[RunCmd] 命令解析失败 ({e})，回退到 shell=True")
        return command, True


def _truncate_output(output: str, max_bytes: int) -> tuple[str, bool]:
    """
    智能截断输出（头部 + 尾部）。
    
    保留开头和结尾信息，对 LLM 更有价值。
    
    Args:
        output: 原始输出
        max_bytes: 最大字节数
    
    Returns:
        (truncated_output, was_truncated)
    """
    output_bytes = output.encode("utf-8", errors="ignore")
    if len(output_bytes) <= max_bytes:
        return output, False
    
    # 头部 33%，尾部 67%（尾部通常包含更重要的结果）
    head_bytes = max_bytes // 3
    tail_bytes = max_bytes - head_bytes - 60  # 预留空间给省略标记
    
    # 截取头部
    head = output_bytes[:head_bytes].decode("utf-8", errors="replace")
    # 确保在完整行结束
    last_newline = head.rfind('\n')
    if last_newline > 0:
        head = head[:last_newline + 1]
    
    # 截取尾部
    tail = output_bytes[-tail_bytes:].decode("utf-8", errors="replace")
    # 确保从完整行开始
    first_newline = tail.find('\n')
    if first_newline > 0:
        tail = tail[first_newline + 1:]
    
    # 计算省略的字节数
    skipped = len(output_bytes) - len(head.encode()) - len(tail.encode())
    
    return f"{head}\n... [省略 {skipped} 字节] ...\n{tail}", True


def run_cmd(
    *,
    workspace_root: Path,
    max_output_bytes: int,
    command: str,
    cwd: str = ".",
    timeout_s: int | None = None,
) -> ToolResult:
    """
    执行命令（安全优化版本）。
    
    优化特性（Phase 3）：
    - 智能 shell 检测：不含 shell 特性时使用 shell=False（更安全）
    - 头尾截断：保留输出的开头和结尾（而非仅尾部）
    - 环境脱敏：只保留安全的环境变量

    注意：更强的策略控制应在 policy/verification 层实现（例如 allowlist/denylist）。
    """
    # 检查工具是否启用
    config = get_command_config()
    if not config.enabled:
        _logger.warning("[RunCmd] 命令执行工具已被禁用")
        return ToolResult(False, error={"code": "E_TOOL_DISABLED", "message": "command tool is disabled"})

    _logger.debug(f"[RunCmd] 开始执行命令: {command}, cwd={cwd}")
    wd = resolve_in_workspace(workspace_root, cwd)
    eff_timeout = int(timeout_s or getattr(config, "timeout_s", 30) or 30)
    if eff_timeout < 1:
        eff_timeout = 1

    # 智能解析命令（安全优化）
    args, use_shell = _parse_command(command)

    # Env scrub：保留常见无敏感变量；Windows 需要 SystemRoot/ComSpec 才更稳
    safe_keys = {
        "PATH",
        "HOME",
        "USER",
        "LANG",
        "LC_ALL",
        "TERM",
        "PWD",
        "SHELL",
        "SYSTEMROOT",
        "COMSPEC",
        "WINDIR",
        "TEMP",
        "TMP",
    }
    scrubbed_env = {k: v for k, v in os.environ.items() if k.upper() in safe_keys or k.startswith("PYTHON")}

    try:
        _logger.debug(f"[RunCmd] 执行命令: {command}, shell={use_shell}, 工作目录: {wd}")
        cp = subprocess.run(
            args,
            cwd=str(wd),
            shell=use_shell,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=scrubbed_env,
            timeout=eff_timeout,
        )
        _logger.info(f"[RunCmd] 命令执行完成: {command}, 返回码: {cp.returncode}, 输出大小: {len(cp.stdout)} bytes, shell={use_shell}")
    except subprocess.TimeoutExpired:
        _logger.warning(f"[RunCmd] 命令超时: {command} (timeout_s={eff_timeout})")
        return ToolResult(False, error={"code": "E_TIMEOUT", "message": f"command timed out after {eff_timeout}s"})
    except FileNotFoundError as e:
        _logger.warning(f"[RunCmd] 命令未找到: {command}, 错误: {e}")
        return ToolResult(False, error={"code": "E_NOT_FOUND", "message": f"command not found: {e}"})
    except Exception as e:
        _logger.error(f"[RunCmd] 命令执行失败: {command}, 错误: {e}", exc_info=True)
        return ToolResult(False, error={"code": "E_EXEC", "message": str(e)})

    # 合并输出
    out = (cp.stdout or "") + (cp.stderr or "")
    
    # 智能截断（头部 + 尾部）
    out, was_truncated = _truncate_output(out, max_output_bytes)
    
    return ToolResult(True, payload={
        "command": command,
        "cwd": cwd,
        "exit_code": cp.returncode,
        "output": out,
        "shell_mode": use_shell,
        "truncated": was_truncated,
    })


