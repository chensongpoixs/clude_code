from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from ..types import ToolResult
from ..workspace import resolve_in_workspace
from ..logger_helper import get_tool_logger
from ...config.tools_config import get_search_config

# 工具模块 logger（延迟初始化）
_logger = get_tool_logger(__name__)


_NOISE_DIRS = {".git", ".clude", "node_modules", ".venv", "dist", "build"}


def grep(*, workspace_root: Path, pattern: str, path: str = ".", ignore_case: bool = False, max_hits: int = 200) -> ToolResult:
    """
    优先使用 ripgrep（rg）以获得更稳定性能和结构化输出；无 rg 时回退到 Python 扫描。
    """
    # 检查工具是否启用
    config = get_search_config()
    if not config.enabled:
        _logger.warning("[Grep] 搜索工具已被禁用")
        return ToolResult(False, error={"code": "E_TOOL_DISABLED", "message": "search tool is disabled"})

    _logger.debug(f"[Grep] 开始搜索: pattern={pattern}, path={path}, ignore_case={ignore_case}, max_hits={max_hits}")
    if shutil.which("rg"):
        _logger.debug("[Grep] 使用 ripgrep (rg)")
        tr = _rg_grep(workspace_root=workspace_root, pattern=pattern, path=path, ignore_case=ignore_case, max_hits=max_hits)
        if tr.ok:
            _logger.info(f"[Grep] ripgrep 搜索成功: 找到 {len(tr.payload.get('matches', [])) if tr.payload else 0} 个匹配")
            return tr
        _logger.warning("[Grep] ripgrep 搜索失败，回退到 Python 扫描")
    else:
        _logger.debug("[Grep] ripgrep 不可用，使用 Python 扫描")
    return _python_grep(workspace_root=workspace_root, pattern=pattern, path=path, ignore_case=ignore_case, max_hits=max_hits)


def _rg_grep(*, workspace_root: Path, pattern: str, path: str, ignore_case: bool, max_hits: int) -> ToolResult:
    root = resolve_in_workspace(workspace_root, path)
    if not root.exists():
        return ToolResult(False, error={"code": "E_NOT_FOUND", "message": f"path not found: {path}"})

    args = ["rg", "--json"]
    if ignore_case:
        args.append("-i")

    # 默认忽略：降低噪音（尤其是 agent 自己的日志目录）
    args.extend(["-g", "!.clude/*", "-g", "!.git/*", "-g", "!node_modules/*", "-g", "!.venv/*"])
    args.append(pattern)
    args.append(path)

    try:
        cp = subprocess.run(
            args,
            cwd=str(workspace_root.resolve()),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
        )
    except Exception as e:
        return ToolResult(False, error={"code": "E_RG_EXEC", "message": str(e)})

    # rg: returncode=1 表示没匹配，视为 ok
    if cp.returncode not in (0, 1):
        return ToolResult(False, error={"code": "E_RG", "message": "rg failed", "details": {"stderr": (cp.stderr or "")[:2000]}})

    hits: list[dict[str, Any]] = []
    for line in (cp.stdout or "").splitlines():
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict) or obj.get("type") != "match":
            continue
        data = obj.get("data") or {}
        p = (((data.get("path") or {}).get("text")) if isinstance(data.get("path"), dict) else None) or ""
        ln = data.get("line_number") if "line_number" in data else None
        lines = (data.get("lines") or {}).get("text") if isinstance(data.get("lines"), dict) else ""
        hits.append({"path": p, "line": ln, "preview": str(lines)[:300]})

    truncated = False
    if len(hits) > max_hits:
        truncated = True
        hits = hits[:max_hits]

    return ToolResult(True, payload={"pattern": pattern, "engine": "rg", "hits": hits, "truncated": truncated})


def _python_grep(*, workspace_root: Path, pattern: str, path: str, ignore_case: bool, max_hits: int) -> ToolResult:
    root = resolve_in_workspace(workspace_root, path)
    if not root.exists():
        return ToolResult(False, error={"code": "E_NOT_FOUND", "message": f"path not found: {path}"})
    flags = re.IGNORECASE if ignore_case else 0
    try:
        rx = re.compile(pattern, flags)
    except re.error as e:
        return ToolResult(False, error={"code": "E_INVALID_REGEX", "message": str(e)})

    hits: list[dict[str, Any]] = []
    for fp in root.rglob("*"):
        if fp.is_dir():
            continue
        if any(part in fp.parts for part in _NOISE_DIRS):
            continue
        try:
            if fp.stat().st_size > 2_000_000:
                continue
            content = fp.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for i, line in enumerate(content.splitlines(), start=1):
            if rx.search(line):
                rel = str(fp.resolve().relative_to(workspace_root.resolve()))
                hits.append({"path": rel, "line": i, "preview": line[:300]})
                if len(hits) >= max_hits:
                    return ToolResult(True, payload={"pattern": pattern, "engine": "python", "hits": hits, "truncated": True})

    return ToolResult(True, payload={"pattern": pattern, "engine": "python", "hits": hits, "truncated": False})


