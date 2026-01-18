from __future__ import annotations

"""
控制协议（Control Protocol / 控制信号协议）

模块职责 (Module Responsibility)：
- 定义 Agent 与 LLM 之间的结构化控制信号协议
- 替代脆弱的字符串匹配（如 STEP_DONE/REPLAN），改用 JSON 信封（JSON Envelope/JSON 信封）
- 提供解析函数，支持协议降级（向下兼容）

设计原则 (Design Principles)：
1. 结构化优先：使用 Pydantic 模型定义协议，运行时自动校验
2. 快速失败：非法输入直接返回 None，由上层决定降级策略
3. 可观测性：保留 reason 字段用于审计追踪

业界对齐 (Industry Alignment)：
- Claude Code / OpenCode 等工具使用结构化"控制通道"，避免模型自由文本误触控制信号
- 参考 JSON-RPC 2.0 协议设计思想

使用示例 (Usage Example)：
    >>> from clude_code.orchestrator.agent_loop.control_protocol import try_parse_control_envelope
    >>> ctrl = try_parse_control_envelope('{"control": "step_done"}')
    >>> if ctrl is not None and ctrl.control == "step_done":
    ...     print("步骤完成")
"""

import json
import logging
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

# P1-1: 模块级 logger，用于调试时追踪解析失败（默认 DEBUG 级别，不影响正常运行）
_logger = logging.getLogger(__name__)


ControlKind = Literal["step_done", "replan"]
"""控制信号类型（ControlKind）：step_done=步骤完成 / replan=需要重规划"""


class ControlEnvelope(BaseModel):
    """
    控制信号信封（Control Envelope / 控制信号信封）。
    
    用于 Agent 与 LLM 之间的控制通道，替代脆弱的字符串匹配。
    
    Attributes:
        control: 控制信号类型（step_done/replan）
        reason: 可选，触发原因（用于审计追踪）
    
    JSON 示例：
        {"control": "step_done"}
        {"control": "replan", "reason": "步骤 3 失败，需要调整计划"}
    """

    control: ControlKind = Field(description="控制信号类型：step_done=步骤完成 / replan=需要重规划")
    reason: str | None = Field(
        default=None, description="可选：为什么触发该控制信号（用于可观测性/审计追踪）"
    )


def try_parse_control_envelope(text: str) -> ControlEnvelope | None:
    """
    尝试从模型输出中解析控制信封（Control Envelope）。
    
    解析规则（Parsing Rules）：
    1. 仅接受单个 JSON 对象（不支持数组或嵌套结构）
    2. 必须包含字段 control，值为 step_done 或 replan
    3. 解析失败返回 None（由上层决定是否走兼容字符串路径）
    
    快速失败策略（Fail-Fast Strategy）：
    - 空输入 → None
    - 不是 `{...}` 结构 → None（快速剪枝，避免不必要的 JSON 解析）
    - JSON 解析失败 → None
    - Pydantic 校验失败 → None
    
    Args:
        text: 模型输出的原始文本
        
    Returns:
        ControlEnvelope: 解析成功时返回结构化控制信号
        None: 解析失败时返回 None
        
    Example:
        >>> try_parse_control_envelope('{"control": "step_done"}')
        ControlEnvelope(control='step_done', reason=None)
        >>> try_parse_control_envelope('STEP_DONE')  # 旧协议
        None
    """
    # 1. 空输入快速返回
    s = (text or "").strip()
    if not s:
        return None

    # 2. 快速剪枝：不是 JSON 对象开头就直接失败（性能优化）
    if not (s.startswith("{") and s.endswith("}")):
        return None

    # 3. 尝试 JSON 解析
    try:
        obj = json.loads(s)
    except Exception as e:
        # P1-1: 快速失败设计，DEBUG 级别日志便于调试（不影响正常运行）
        _logger.debug(f"ControlEnvelope JSON 解析失败: {e} [input={s[:50]}...]")
        return None

    # 4. 必须是 dict 类型
    if not isinstance(obj, dict):
        _logger.debug(f"ControlEnvelope 非 dict 类型: {type(obj).__name__}")
        return None

    # 5. 尝试 Pydantic 校验
    try:
        return ControlEnvelope.model_validate(obj)
    except ValidationError as e:
        # P1-1: 快速失败设计，DEBUG 级别日志便于调试（不影响正常运行）
        _logger.debug(f"ControlEnvelope Pydantic 校验失败: {e}")
        return None


