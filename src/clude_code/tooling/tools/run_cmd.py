from __future__ import annotations

import os
import subprocess
from pathlib import Path

from ..types import ToolResult
from ..workspace import resolve_in_workspace


def run_cmd(*, workspace_root: Path, max_output_bytes: int, command: str, cwd: str = ".") -> ToolResult:
    """
    执行命令（MVP：shell=True），并做基础环境变量脱敏，限制输出大小。

    注意：更强的策略控制应在 policy/verification 层实现（例如 allowlist/denylist）。
    """
    wd = resolve_in_workspace(workspace_root, cwd)

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
        cp = subprocess.run(
            command,
            cwd=str(wd),
            shell=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=scrubbed_env,
        )
    except Exception as e:
        return ToolResult(False, error={"code": "E_EXEC", "message": str(e)})

    out = (cp.stdout or "") + (cp.stderr or "")
    if len(out.encode("utf-8", errors="ignore")) > max_output_bytes:
        out = out[-max_output_bytes:]
    return ToolResult(True, payload={"command": command, "cwd": cwd, "exit_code": cp.returncode, "output": out})


