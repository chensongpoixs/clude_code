from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class CommandDecision:
    ok: bool
    reason: str = ""


DEFAULT_DENYLIST = [
    # destructive filesystem
    r"\brm\s+-rf\b",
    r"\bdel\s+/f\b",
    r"\bformat\s+[a-z]:\b",
    r"\bmkfs\.",
    # remote fetch/exec (network)
    r"\bcurl\b",
    r"\bwget\b",
    r"\binvoke-webrequest\b",
    r"\birm\b",  # PowerShell Invoke-RestMethod alias
    # privilege escalation
    r"\bsudo\b",
]


def evaluate_command(command: str, *, allow_network: bool) -> CommandDecision:
    """
    兼容性函数：保持原有接口，同时使用新的安全策略系统
    """
    from clude_code.policy.advanced_security import (
        get_security_policy, SecurityContext, evaluate_command_with_context
    )

    cmd = command.strip()
    if not cmd:
        return CommandDecision(False, "empty command")

    # 创建安全上下文
    security_context = SecurityContext(
        network_enabled=allow_network,
        risk_threshold=RiskLevel.MEDIUM  # 默认中等风险阈值
    )

    # 使用新的安全策略系统评估
    allowed, reason, risk_level = evaluate_command_with_context(
        cmd, {"allow_network": allow_network}, security_context
    )

    if not allowed:
        return CommandDecision(False, reason)

    return CommandDecision(True, "")


