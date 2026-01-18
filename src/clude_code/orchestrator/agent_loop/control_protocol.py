from __future__ import annotations

"""
控制协议（Control Protocol / 控制信号协议）

目标：
- 替代脆弱的字符串匹配（如 STEP_DONE/REPLAN），改用结构化 JSON 信封（JSON Envelope/JSON 信封）。
- 兼容旧协议：若模型仍输出字符串，允许降级识别，但必须记录告警，推动迁移。

业界对齐：
- Claude Code / OpenCode 等工具会用结构化“控制通道”，避免模型自由文本误触控制信号。
"""

import json
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError


ControlKind = Literal["step_done", "replan"]


class ControlEnvelope(BaseModel):
    """控制信号信封（Control Envelope / 控制信号信封）。"""

    control: ControlKind = Field(description="控制信号类型：step_done/replan")
    reason: str | None = Field(
        default=None, description="可选：为什么触发该控制信号（用于可观测性）"
    )


def try_parse_control_envelope(text: str) -> ControlEnvelope | None:
    """
    尝试从模型输出中解析控制信封。

    规则：
    - 仅接受单个 JSON 对象。
    - 必须包含字段 control。
    - 解析失败返回 None（由上层决定是否走兼容字符串路径）。
    """

    s = (text or "").strip()
    if not s:
        return None

    # 快速剪枝：不是 JSON 对象开头就直接失败
    if not (s.startswith("{") and s.endswith("}")):
        return None

    try:
        obj = json.loads(s)
    except Exception:
        return None

    if not isinstance(obj, dict):
        return None

    try:
        return ControlEnvelope.model_validate(obj)
    except ValidationError:
        return None


