from __future__ import annotations

from pathlib import Path
from typing import Any

from ..types import ToolResult
from ..workspace import resolve_in_workspace
from ..logger_helper import get_tool_logger
from ...config.tools_config import get_file_config

# 工具模块 logger（延迟初始化）
_logger = get_tool_logger(__name__)


def read_file(
    *,
    workspace_root: Path,
    max_file_read_bytes: int,
    path: str,
    offset: int | None = None,
    limit: int | None = None,
) -> ToolResult:
    """
    读取文件（带尺寸上限、编码容错、可选的按行切片）。
    """
    # 检查工具是否启用
    config = get_file_config()
    if not config.enabled:
        _logger.warning("[ReadFile] 文件读取工具已被禁用")
        return ToolResult(False, error={"code": "E_TOOL_DISABLED", "message": "file tool is disabled"})

    try:
        _logger.debug(f"[ReadFile] 开始读取文件: {path}, offset={offset}, limit={limit}")
        p = resolve_in_workspace(workspace_root, path)
        if not p.exists() or not p.is_file():
            _logger.warning(f"[ReadFile] 文件不存在或不是文件: {path}")
            return ToolResult(False, error={"code": "E_NOT_FILE", "message": f"not a file: {path}"})

        file_size = p.stat().st_size
        _logger.debug(f"[ReadFile] 文件大小: {file_size} bytes, 限制: {max_file_read_bytes} bytes")
        data = p.read_bytes()

        truncated = False
        if len(data) > max_file_read_bytes:
            data = data[:max_file_read_bytes]
            truncated = True
            _logger.warning(f"[ReadFile] 文件过大，已截断: {file_size} -> {max_file_read_bytes} bytes")

        text = data.decode("utf-8", errors="replace")
        lines = text.splitlines()
        _logger.debug(f"[ReadFile] 成功读取: {len(lines)} 行, 实际大小: {len(data)} bytes")

        res_payload: dict[str, Any] = {
            "path": path,
            "total_size": file_size,
            "read_size": len(data),
            "truncated": truncated,
        }
        if truncated:
            res_payload["warning"] = (
                f"File is too large ({file_size} bytes). Output truncated to {max_file_read_bytes} bytes."
            )

        if offset is None and limit is None:
            res_payload["text"] = text
            return ToolResult(True, payload=res_payload)

        start = max((offset or 1) - 1, 0)
        count = limit or 200
        end = min(start + count, len(lines))

        res_payload["text"] = "\n".join(lines[start:end])
        res_payload["offset"] = offset
        res_payload["limit"] = limit
        _logger.info(f"[ReadFile] 读取成功: {path}, 返回行数: {end - start}")
        return ToolResult(True, payload=res_payload)
    except Exception as e:
        _logger.error(f"[ReadFile] 读取失败: {path}, 错误: {e}", exc_info=True)
        return ToolResult(False, error={"code": "E_READ", "message": "[workspace_root:" + str(workspace_root) +"][max_file_read_bytes:"+str(max_file_read_bytes)+"][path:"+path+"][offset:"+str(offset)+"][limit:"+str(limit)+"][ e: "+str(e)+"]"})


