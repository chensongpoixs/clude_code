from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class AgentTurn:
    """
    Agent 一轮对话的返回结果。

    属性:
        assistant_text: Agent 的最终回复文本（如果未调用工具，则为完整回复；否则为最后一轮的工具调用结果）
        tool_used: 本轮是否使用了工具
        trace_id: 本轮对话的唯一追踪ID（用于日志关联）
        events: 本轮所有事件的列表（用于调试和可观测性）
    """

    assistant_text: str
    tool_used: bool
    trace_id: str
    events: list[dict[str, Any]]


