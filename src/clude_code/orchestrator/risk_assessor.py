from __future__ import annotations

from dataclasses import dataclass

from clude_code.orchestrator.registry.schema import RiskLevel


@dataclass(frozen=True)
class PlanRiskAssessment:
    risk_level: RiskLevel
    reason: str


_RISK_ORDER: dict[RiskLevel, int] = {
    RiskLevel.LOW: 1,
    RiskLevel.MEDIUM: 2,
    RiskLevel.HIGH: 3,
    RiskLevel.CRITICAL: 4,
}


def _max_risk(a: RiskLevel, b: RiskLevel) -> RiskLevel:
    return a if _RISK_ORDER[a] >= _RISK_ORDER[b] else b


def assess_plan_risk(plan) -> PlanRiskAssessment:
    """
    基于 Plan.steps[*].tools_expected 推导计划级风险（MVP）。

    设计目标：
    - 防止 intent 风险误配（例如 intent=LOW 但 plan 包含 run_cmd/write_file）
    - 仅做“上浮”，不做复杂静态分析（Phase 2 可运营闭环优先）
    """
    tools: set[str] = set()
    try:
        for s in getattr(plan, "steps", []) or []:
            for t in (getattr(s, "tools_expected", None) or []):
                if isinstance(t, str) and t.strip():
                    tools.add(t.strip())
    except Exception:
        return PlanRiskAssessment(risk_level=RiskLevel.MEDIUM, reason="无法解析 steps.tools_expected，按 MEDIUM 兜底")

    risk = RiskLevel.LOW
    reasons: list[str] = []

    # write/delete 类
    if tools & {"write_file", "apply_patch", "undo_patch"}:
        risk = _max_risk(risk, RiskLevel.HIGH)
        reasons.append("包含写操作工具(write_file/apply_patch/undo_patch)")
    if tools & {"delete_file"}:
        risk = _max_risk(risk, RiskLevel.CRITICAL)
        reasons.append("包含删除操作工具(delete_file)")

    # exec 类
    if tools & {"run_cmd"}:
        risk = _max_risk(risk, RiskLevel.CRITICAL)
        reasons.append("包含命令执行工具(run_cmd)")

    # network 类（按现有工具划分，websearch/webfetch/codesearch 为网络依赖）
    if tools & {"websearch", "webfetch", "codesearch"}:
        risk = _max_risk(risk, RiskLevel.MEDIUM)
        reasons.append("包含网络依赖工具(websearch/webfetch/codesearch)")

    if not reasons:
        reasons.append("仅只读/低风险工具")

    return PlanRiskAssessment(risk_level=risk, reason="; ".join(reasons))


def merge_intent_and_plan_risk(intent_risk: RiskLevel, plan_risk: RiskLevel) -> RiskLevel:
    """最终风险取最大值。"""
    return _max_risk(intent_risk, plan_risk)


