"""
高级安全策略系统
参考Claude Code，实现细粒度的权限控制和动态风险评估
"""
import re
import hashlib
from typing import Dict, List, Any, Optional, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class RiskLevel(Enum):
    """风险等级"""
    SAFE = "safe"         # 安全操作
    LOW = "low"          # 低风险
    MEDIUM = "medium"    # 中等风险
    HIGH = "high"        # 高风险
    CRITICAL = "critical" # 严重风险


class PermissionScope(Enum):
    """权限范围"""
    READ = "read"           # 只读操作
    WRITE = "write"         # 写入操作
    EXECUTE = "execute"     # 执行操作
    NETWORK = "network"     # 网络操作
    SYSTEM = "system"       # 系统级操作
    ADMIN = "admin"         # 管理员操作


@dataclass
class SecurityContext:
    """安全上下文"""
    user_id: str = "default"
    session_id: str = ""
    workspace_root: Path = field(default_factory=lambda: Path("."))
    allowed_scopes: Set[PermissionScope] = field(default_factory=lambda: {
        PermissionScope.READ, PermissionScope.WRITE
    })
    risk_threshold: RiskLevel = RiskLevel.MEDIUM
    network_enabled: bool = False
    audit_enabled: bool = True

    def can_access_scope(self, scope: PermissionScope) -> bool:
        """检查是否可以访问指定范围"""
        return scope in self.allowed_scopes

    def is_risk_acceptable(self, risk: RiskLevel) -> bool:
        """检查风险等级是否可接受"""
        risk_order = [RiskLevel.SAFE, RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL]
        return risk_order.index(risk) <= risk_order.index(self.risk_threshold)


@dataclass
class SecurityRule:
    """安全规则"""
    id: str
    name: str
    description: str
    risk_level: RiskLevel
    scope: PermissionScope
    patterns: List[str] = field(default_factory=list)
    conditions: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True

    def matches(self, command: str, context: Dict[str, Any]) -> Tuple[bool, str]:
        """
        检查命令是否匹配规则

        Returns:
            (是否匹配, 匹配原因)
        """
        if not self.enabled:
            return False, ""

        # 检查模式匹配
        for pattern in self.patterns:
            if re.search(pattern, command, re.IGNORECASE):
                return True, f"匹配模式: {pattern}"

        # 检查条件匹配
        for key, expected_value in self.conditions.items():
            if key in context:
                actual_value = context[key]
                if self._check_condition(actual_value, expected_value):
                    return True, f"匹配条件: {key}={actual_value}"

        return False, ""


class AdvancedSecurityPolicy:
    """
    高级安全策略管理器
    实现动态权限控制和风险评估
    """

    def __init__(self):
        self.rules: Dict[str, SecurityRule] = {}
        self.audit_log: List[Dict[str, Any]] = []
        self.max_audit_entries = 1000

        # 初始化默认规则
        self._initialize_default_rules()

    def _initialize_default_rules(self):
        """初始化默认安全规则"""

        # 文件系统安全规则
        self.add_rule(SecurityRule(
            id="fs_read_safe",
            name="安全文件读取",
            description="允许读取常见文件类型",
            risk_level=RiskLevel.SAFE,
            scope=PermissionScope.READ,
            patterns=[
                r"\bread_file\b.*\.(txt|md|py|js|ts|json|yaml|yml|xml|csv)$",
                r"\blist_dir\b"
            ]
        ))

        self.add_rule(SecurityRule(
            id="fs_write_restricted",
            name="受限文件写入",
            description="限制写入敏感文件",
            risk_level=RiskLevel.HIGH,
            scope=PermissionScope.WRITE,
            patterns=[
                r"\bapply_patch\b.*\.(config|conf|ini|env|key|pem|crt)$",
                r"\bwrite_file\b.*\.(exe|dll|so|dylib)$",
                r"\bapply_patch\b.*\b(__pycache__|node_modules|\.git)\b"
            ]
        ))

        # 命令执行安全规则
        self.add_rule(SecurityRule(
            id="cmd_destructive",
            name="破坏性命令",
            description="禁止执行破坏性命令",
            risk_level=RiskLevel.CRITICAL,
            scope=PermissionScope.EXECUTE,
            patterns=[
                r"\brm\s+-rf\b",
                r"\bdel\s+/f\s+/q\b",
                r"\bformat\s+[a-z]:\b",
                r"\bmkfs\b",
                r"\bfdisk\b",
                r"\bdd\s+if=/dev/zero\b"
            ]
        ))

        self.add_rule(SecurityRule(
            id="cmd_privilege",
            name="权限提升",
            description="禁止权限提升命令",
            risk_level=RiskLevel.CRITICAL,
            scope=PermissionScope.EXECUTE,
            patterns=[
                r"\bsudo\b",
                r"\bsu\b",
                r"\brunuser\b",
                r"\bsetuid\b",
                r"\bchown\b.*root",
                r"\bchmod\b.*777"
            ]
        ))

        # 网络安全规则
        self.add_rule(SecurityRule(
            id="network_fetch",
            name="网络获取",
            description="控制网络下载命令",
            risk_level=RiskLevel.MEDIUM,
            scope=PermissionScope.NETWORK,
            patterns=[
                r"\bcurl\b",
                r"\bwget\b",
                r"\bgit clone\b",
                r"\binvoke-webrequest\b",
                r"\birm\b"
            ]
        ))

        # 系统操作规则
        self.add_rule(SecurityRule(
            id="system_install",
            name="系统安装",
            description="控制系统包安装",
            risk_level=RiskLevel.HIGH,
            scope=PermissionScope.SYSTEM,
            patterns=[
                r"\bapt\b.*\binstall\b",
                r"\bpip\b.*\binstall\b",
                r"\bnpm\b.*\binstall\b",
                r"\byarn\b.*\badd\b",
                r"\bbrew\b.*\binstall\b"
            ]
        ))

    def add_rule(self, rule: SecurityRule) -> None:
        """添加安全规则"""
        self.rules[rule.id] = rule

    def remove_rule(self, rule_id: str) -> bool:
        """移除安全规则"""
        if rule_id in self.rules:
            del self.rules[rule_id]
            return True
        return False

    def evaluate_operation(self, operation: str, context: Dict[str, Any],
                          security_context: SecurityContext) -> Tuple[bool, str, RiskLevel]:
        """
        评估操作的安全性

        Args:
            operation: 操作描述（如命令字符串、工具名等）
            context: 操作上下文信息
            security_context: 安全上下文

        Returns:
            (是否允许, 拒绝原因, 风险等级)
        """
        # 检查权限范围
        required_scope = self._infer_scope_from_operation(operation)
        if not security_context.can_access_scope(required_scope):
            return False, f"权限不足: 需要 {required_scope.value} 权限", RiskLevel.CRITICAL

        # 评估风险等级
        risk_level = self._assess_risk_level(operation, context)

        # 检查是否超过风险阈值
        if not security_context.is_risk_acceptable(risk_level):
            return False, f"操作风险过高: {risk_level.value}", risk_level

        # 检查具体规则
        for rule in self.rules.values():
            if not rule.enabled:
                continue

            matches, reason = rule.matches(operation, context)
            if matches:
                if rule.risk_level.value in ['high', 'critical']:
                    # 高风险操作需要额外确认
                    return False, f"安全规则拦截: {rule.name} - {reason}", rule.risk_level

        # 记录审计日志
        self._audit_operation(operation, context, security_context, True, "")

        return True, "", risk_level

    def _infer_scope_from_operation(self, operation: str) -> PermissionScope:
        """从操作推断所需权限范围"""
        operation_lower = operation.lower()

        # 检测网络操作
        if any(keyword in operation_lower for keyword in ['curl', 'wget', 'http', 'https', 'git clone']):
            return PermissionScope.NETWORK

        # 检测执行操作
        if any(keyword in operation_lower for keyword in ['run_cmd', 'exec', 'system']):
            return PermissionScope.EXECUTE

        # 检测写入操作
        if any(keyword in operation_lower for keyword in ['write_file', 'apply_patch', 'create']):
            return PermissionScope.WRITE

        # 默认读取操作
        return PermissionScope.READ

    def _assess_risk_level(self, operation: str, context: Dict[str, Any]) -> RiskLevel:
        """评估操作的风险等级"""
        operation_lower = operation.lower()

        # 最高风险操作
        if any(pattern in operation_lower for pattern in [
            'rm -rf', 'format', 'mkfs', 'dd if=/dev/zero', 'sudo', 'chmod 777'
        ]):
            return RiskLevel.CRITICAL

        # 高风险操作
        if any(pattern in operation_lower for pattern in [
            'pip install', 'npm install', 'apt install', 'systemctl', 'service'
        ]):
            return RiskLevel.HIGH

        # 中等风险操作
        if any(pattern in operation_lower for pattern in [
            'curl', 'wget', 'git clone', 'chmod', 'chown'
        ]):
            return RiskLevel.MEDIUM

        # 低风险操作
        if any(pattern in operation_lower for pattern in [
            'ls', 'cat', 'grep', 'find', 'read_file', 'list_dir'
        ]):
            return RiskLevel.LOW

        # 默认安全
        return RiskLevel.SAFE

    def _audit_operation(self, operation: str, context: Dict[str, Any],
                        security_context: SecurityContext, allowed: bool, reason: str) -> None:
        """记录操作审计日志"""
        if not security_context.audit_enabled:
            return

        audit_entry = {
            "timestamp": self._get_timestamp(),
            "user_id": security_context.user_id,
            "session_id": security_context.session_id,
            "operation": operation,
            "context": context,
            "allowed": allowed,
            "reason": reason,
            "risk_level": self._assess_risk_level(operation, context).value,
            "workspace": str(security_context.workspace_root)
        }

        self.audit_log.append(audit_entry)

        # 限制审计日志大小
        if len(self.audit_log) > self.max_audit_entries:
            self.audit_log = self.audit_log[-self.max_audit_entries:]

    def get_audit_log(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取审计日志"""
        return self.audit_log[-limit:] if self.audit_log else []

    def get_security_report(self) -> Dict[str, Any]:
        """生成安全报告"""
        if not self.audit_log:
            return {"total_operations": 0, "blocked_operations": 0}

        total_ops = len(self.audit_log)
        blocked_ops = len([entry for entry in self.audit_log if not entry["allowed"]])

        risk_distribution = {}
        for entry in self.audit_log:
            risk = entry["risk_level"]
            risk_distribution[risk] = risk_distribution.get(risk, 0) + 1

        return {
            "total_operations": total_ops,
            "blocked_operations": blocked_ops,
            "allowed_operations": total_ops - blocked_ops,
            "block_rate": blocked_ops / total_ops if total_ops > 0 else 0,
            "risk_distribution": risk_distribution,
            "active_rules": len([r for r in self.rules.values() if r.enabled])
        }

    def _get_timestamp(self) -> str:
        """获取当前时间戳"""
        from datetime import datetime
        return datetime.now().isoformat()

    def _check_condition(self, actual: Any, expected: Any) -> bool:
        """检查条件匹配"""
        if isinstance(expected, str) and expected.startswith("regex:"):
            pattern = expected[6:]  # Remove "regex:" prefix
            return bool(re.search(pattern, str(actual), re.IGNORECASE))

        return str(actual).lower() == str(expected).lower()


class PermissionManager:
    """
    权限管理器
    管理用户权限和动态授权
    """

    def __init__(self):
        self.user_permissions: Dict[str, Set[PermissionScope]] = {}
        self.temporary_grants: Dict[str, Dict[str, Any]] = {}  # session_id -> grants

    def grant_permission(self, user_id: str, scope: PermissionScope,
                        temporary: bool = False, session_id: str = "") -> None:
        """授予权限"""
        if user_id not in self.user_permissions:
            self.user_permissions[user_id] = set()

        self.user_permissions[user_id].add(scope)

        if temporary and session_id:
            if session_id not in self.temporary_grants:
                self.temporary_grants[session_id] = {}
            self.temporary_grants[session_id][scope] = True

    def revoke_permission(self, user_id: str, scope: PermissionScope) -> None:
        """撤销权限"""
        if user_id in self.user_permissions:
            self.user_permissions[user_id].discard(scope)

    def has_permission(self, user_id: str, scope: PermissionScope) -> bool:
        """检查权限"""
        return scope in self.user_permissions.get(user_id, set())

    def clear_temporary_grants(self, session_id: str) -> None:
        """清除临时权限"""
        if session_id in self.temporary_grants:
            del self.temporary_grants[session_id]


# 全局安全策略实例
_security_policy: Optional[AdvancedSecurityPolicy] = None
_permission_manager: Optional[PermissionManager] = None

def get_security_policy() -> AdvancedSecurityPolicy:
    """获取安全策略管理器"""
    global _security_policy
    if _security_policy is None:
        _security_policy = AdvancedSecurityPolicy()
    return _security_policy

def get_permission_manager() -> PermissionManager:
    """获取权限管理器"""
    global _permission_manager
    if _permission_manager is None:
        _permission_manager = PermissionManager()
    return _permission_manager

def evaluate_command_with_context(command: str, context: Dict[str, Any],
                                security_context: SecurityContext) -> Tuple[bool, str, RiskLevel]:
    """
    增强的命令评估函数，包含上下文信息

    Args:
        command: 命令字符串
        context: 上下文信息（如工作目录、文件路径等）
        security_context: 安全上下文

    Returns:
        (是否允许, 原因, 风险等级)
    """
    policy = get_security_policy()
    return policy.evaluate_operation(command, context, security_context)