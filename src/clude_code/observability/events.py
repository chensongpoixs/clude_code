"""
审计事件类型常量

定义所有标准化审计事件，确保可追溯性和一致性。
对齐 agent_design_v_1.0.md 设计规范第8节。
"""

from enum import Enum


class AuditEventType(str, Enum):
    """审计事件类型"""
    
    # 会话生命周期
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    
    # 意图与决策
    INTENT_CLASSIFIED = "intent_classified"
    PROFILE_SELECTED = "profile_selected"
    RISK_EVALUATED = "risk_evaluated"
    PLANNING_STARTED = "planning_started"
    PLANNING_COMPLETED = "planning_completed"
    PLANNING_SKIPPED = "planning_skipped"
    
    # 执行与工具
    TOOL_EXECUTED = "tool_executed"
    TOOL_FAILED = "tool_failed"
    STEP_STARTED = "step_started"
    STEP_COMPLETED = "step_completed"
    STEP_FAILED = "step_failed"
    
    # 风险控制
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_GRANTED = "approval_granted"
    APPROVAL_DENIED = "approval_denied"
    ROLLBACK_CREATED = "rollback_created"
    ROLLBACK_EXECUTED = "rollback_executed"
    
    # LLM 交互
    LLM_REQUEST = "llm_request"
    LLM_RESPONSE = "llm_response"
    LLM_ERROR = "llm_error"
    
    # Prompt 变更
    PROMPT_LOADED = "prompt_loaded"
    PROMPT_VERSION_CHANGED = "prompt_version_changed"


# 关键决策点（必须记录）
CRITICAL_EVENTS = {
    AuditEventType.INTENT_CLASSIFIED,
    AuditEventType.PROFILE_SELECTED,
    AuditEventType.RISK_EVALUATED,
    AuditEventType.APPROVAL_REQUESTED,
    AuditEventType.APPROVAL_GRANTED,
    AuditEventType.APPROVAL_DENIED,
    AuditEventType.TOOL_EXECUTED,
    AuditEventType.ROLLBACK_EXECUTED,
}


def is_critical_event(event_type: str | AuditEventType) -> bool:
    """判断是否为关键审计事件"""
    if isinstance(event_type, str):
        try:
            event_type = AuditEventType(event_type)
        except ValueError:
            return False
    return event_type in CRITICAL_EVENTS

