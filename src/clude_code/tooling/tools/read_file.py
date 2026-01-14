from __future__ import annotations

from pathlib import Path
from typing import Any

from ..types import ToolResult
from ..workspace import resolve_in_workspace


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
    try:
        p = resolve_in_workspace(workspace_root, path)
        if not p.exists() or not p.is_file():
            return ToolResult(False, error={"code": "E_NOT_FILE", "message": f"not a file: {path}"})

        file_size = p.stat().st_size
        data = p.read_bytes()

        truncated = False
        if len(data) > max_file_read_bytes:
            data = data[:max_file_read_bytes]
            truncated = True

        text = data.decode("utf-8", errors="replace")
        lines = text.splitlines()

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
        return ToolResult(True, payload=res_payload)
    except Exception as e:
        return ToolResult(False, error={"code": "E_READ", "message": "[workspace_root:" + str(workspace_root) +"][max_file_read_bytes:"+str(max_file_read_bytes)+"][path:"+path+"][offset:"+str(offset)+"][limit:"+str(limit)+"][ e: "+str(e)+"]"})


