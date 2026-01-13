from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class ToolError(RuntimeError):
    """工具层通用异常（通常表示不可恢复的调用错误，如越权路径）。"""


@dataclass(frozen=True)
class ToolResult:
    """统一的工具返回结构（供 LLM 回喂/审计/调试使用）。"""

    ok: bool
    payload: dict[str, Any] | None = None
    error: dict[str, Any] | None = None


