"""
风险路由器（Risk Router）

功能：
1. 根据风险等级决定执行策略
2. 实现 Human-in-the-Loop 机制
3. 管理审批流程

对齐 agent_design_v_1.0.md 设计规范第7节：
| 风险等级   | 执行策略         |
|----------|-----------------|
| LOW      | 自动执行         |
| MEDIUM   | 自动执行 + 回滚   |
| HIGH     | Plan Review     |
| CRITICAL | 人工审批 + 沙箱   |
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

from clude_code.orchestrator.registry import RiskLevel


class ExecutionStrategy(str, Enum):
    """执行策略"""
    AUTO = "AUTO"                  # 自动执行
    AUTO_WITH_ROLLBACK = "AUTO_WITH_ROLLBACK"  # 自动执行 + 回滚准备
    PLAN_REVIEW = "PLAN_REVIEW"    # Plan Review（展示计划，确认后执行）
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"   # 人工审批 + 沙箱


@dataclass
class ExecutionDecision:
    """执行决策"""
    strategy: ExecutionStrategy
    risk_level: RiskLevel
    requires_confirmation: bool
    requires_rollback: bool
    requires_sandbox: bool
    message: str = ""


# 风险等级 → 执行策略映射
_RISK_TO_STRATEGY: dict[RiskLevel, ExecutionStrategy] = {
    RiskLevel.LOW: ExecutionStrategy.AUTO,
    RiskLevel.MEDIUM: ExecutionStrategy.AUTO_WITH_ROLLBACK,
    RiskLevel.HIGH: ExecutionStrategy.PLAN_REVIEW,
    RiskLevel.CRITICAL: ExecutionStrategy.APPROVAL_REQUIRED,
}


class RiskRouter:
    """
    风险路由器
    
    根据风险等级和操作类型决定执行策略。
    """
    
    def __init__(self, default_risk_level: RiskLevel = RiskLevel.MEDIUM):
        self.default_risk_level = default_risk_level
        self._high_risk_tools = {
            "run_cmd",      # 命令执行
            "write_file",   # 文件写入
            "apply_patch",  # 代码补丁
        }
        self._critical_tools = {
            "rm", "delete",  # 删除操作（如果有）
        }
    
    def route(
        self,
        risk_level: RiskLevel | None = None,
        tool_name: str | None = None,
        operation_type: str | None = None,
    ) -> ExecutionDecision:
        """
        根据风险等级和操作类型决定执行策略。
        
        参数:
            risk_level: 风险等级（来自 Profile 或 Intent）
            tool_name: 工具名称（可提升风险等级）
            operation_type: 操作类型（可选）
        
        返回:
            ExecutionDecision 决策结果
        """
        effective_risk = risk_level or self.default_risk_level
        
        # 工具可提升风险等级（只升不降）
        if tool_name:
            tool_risk = self._assess_tool_risk(tool_name)
            if tool_risk.value > effective_risk.value:
                effective_risk = tool_risk
        
        strategy = _RISK_TO_STRATEGY.get(effective_risk, ExecutionStrategy.AUTO_WITH_ROLLBACK)
        
        return ExecutionDecision(
            strategy=strategy,
            risk_level=effective_risk,
            requires_confirmation=strategy in (ExecutionStrategy.PLAN_REVIEW, ExecutionStrategy.APPROVAL_REQUIRED),
            requires_rollback=strategy in (ExecutionStrategy.AUTO_WITH_ROLLBACK, ExecutionStrategy.PLAN_REVIEW, ExecutionStrategy.APPROVAL_REQUIRED),
            requires_sandbox=strategy == ExecutionStrategy.APPROVAL_REQUIRED,
            message=self._get_decision_message(strategy, effective_risk),
        )
    
    def _assess_tool_risk(self, tool_name: str) -> RiskLevel:
        """评估工具风险等级"""
        if tool_name in self._critical_tools:
            return RiskLevel.CRITICAL
        if tool_name in self._high_risk_tools:
            return RiskLevel.MEDIUM  # 默认中等，可由配置覆盖
        return RiskLevel.LOW
    
    def _get_decision_message(self, strategy: ExecutionStrategy, risk_level: RiskLevel) -> str:
        """获取决策说明消息"""
        messages = {
            ExecutionStrategy.AUTO: "低风险操作，自动执行",
            ExecutionStrategy.AUTO_WITH_ROLLBACK: "中等风险操作，自动执行并准备回滚",
            ExecutionStrategy.PLAN_REVIEW: f"高风险操作（{risk_level.value}），需要确认执行计划",
            ExecutionStrategy.APPROVAL_REQUIRED: f"关键风险操作（{risk_level.value}），需要人工审批",
        }
        return messages.get(strategy, "")
    
    def should_confirm(
        self,
        risk_level: RiskLevel | None = None,
        tool_name: str | None = None,
    ) -> bool:
        """
        判断是否需要用户确认。
        
        用于工具执行前的检查点。
        """
        decision = self.route(risk_level, tool_name)
        return decision.requires_confirmation
    
    def should_prepare_rollback(
        self,
        risk_level: RiskLevel | None = None,
        tool_name: str | None = None,
    ) -> bool:
        """
        判断是否需要准备回滚。
        
        用于文件操作前的备份。
        """
        decision = self.route(risk_level, tool_name)
        return decision.requires_rollback


# ============================================================
# Human-in-the-Loop 辅助函数
# ============================================================

def format_plan_review_prompt(
    plan_summary: str,
    risk_level: RiskLevel,
    affected_files: list[str] | None = None,
) -> str:
    """
    格式化 Plan Review 提示信息。
    
    用于 HIGH 风险操作的确认对话。
    """
    lines = [
        f"⚠️ 高风险操作确认（风险等级: {risk_level.value}）",
        "",
        "执行计划摘要:",
        plan_summary,
        "",
    ]
    
    if affected_files:
        lines.extend([
            "受影响的文件:",
            *[f"  - {f}" for f in affected_files[:10]],
        ])
        if len(affected_files) > 10:
            lines.append(f"  ... 及其他 {len(affected_files) - 10} 个文件")
        lines.append("")
    
    lines.append("是否继续执行？")
    return "\n".join(lines)


def format_approval_request(
    operation: str,
    risk_level: RiskLevel,
    details: dict[str, Any] | None = None,
) -> str:
    """
    格式化审批请求信息。
    
    用于 CRITICAL 风险操作的审批流程。
    """
    lines = [
        f"🚨 关键操作审批请求（风险等级: {risk_level.value}）",
        "",
        f"操作: {operation}",
        "",
    ]
    
    if details:
        lines.append("详细信息:")
        for k, v in details.items():
            lines.append(f"  {k}: {v}")
        lines.append("")
    
    lines.extend([
        "此操作需要人工审批。",
        "请确认已了解影响范围并准备好回滚方案。",
    ])
    
    return "\n".join(lines)


# ============================================================
# 单例
# ============================================================

_default_router: RiskRouter | None = None


def get_default_risk_router() -> RiskRouter:
    """获取默认风险路由器（单例）"""
    global _default_router
    if _default_router is None:
        _default_router = RiskRouter()
    return _default_router

