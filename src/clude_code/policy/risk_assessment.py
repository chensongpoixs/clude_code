"""
风险评估工具
在工具调用前进行智能风险评估和用户确认
"""
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum


class ConfirmationLevel(Enum):
    """确认级别"""
    NONE = "none"         # 无需确认
    QUIET = "quiet"       # 静默确认（低风险）
    NORMAL = "normal"     # 正常确认
    VERBOSE = "verbose"   # 详细确认
    STRICT = "strict"     # 严格确认（高风险）


@dataclass
class RiskAssessment:
    """风险评估结果"""
    risk_level: str
    confidence: float  # 0-1, 评估置信度
    reasons: List[str]  # 风险原因
    suggestions: List[str]  # 建议措施
    confirmation_required: bool
    confirmation_level: ConfirmationLevel

    def should_confirm(self) -> bool:
        """是否需要确认"""
        return self.confirmation_required

    def get_confirmation_message(self) -> str:
        """获取确认消息"""
        if not self.should_confirm():
            return ""

        risk_indicator = self._get_risk_indicator()
        reasons_text = "\n".join(f"  • {reason}" for reason in self.reasons[:3])

        message = f"""{risk_indicator} 操作风险评估

检测到的风险因素：
{reasons_text}

建议措施：
{chr(10).join(f"  • {suggestion}" for suggestion in self.suggestions[:3])}

置信度: {self.confidence:.1%}
"""

        return message

    def _get_risk_indicator(self) -> str:
        """获取风险指示器"""
        indicators = {
            "low": "🟢 低风险操作",
            "medium": "🟡 中等风险操作",
            "high": "🟠 高风险操作",
            "critical": "🔴 严重风险操作"
        }
        return indicators.get(self.risk_level, "⚪ 未知风险操作")


class RiskAssessor:
    """
    风险评估器
    对工具调用进行智能风险评估
    """

    def __init__(self):
        self.risk_patterns = self._initialize_risk_patterns()

    def _initialize_risk_patterns(self) -> Dict[str, Dict[str, Any]]:
        """初始化风险模式"""
        return {
            # 文件操作风险
            "file_write": {
                "risk_level": "medium",
                "patterns": [r"write_file", r"apply_patch"],
                "risk_factors": ["文件修改可能导致代码损坏"],
                "suggestions": ["建议先备份文件", "检查语法正确性"]
            },
            "file_delete": {
                "risk_level": "high",
                "patterns": [r"rm\s+-rf", r"del\s+/f"],
                "risk_factors": ["删除操作不可逆"],
                "suggestions": ["确认文件路径", "考虑备份重要文件"]
            },

            # 命令执行风险
            "system_commands": {
                "risk_level": "high",
                "patterns": [r"sudo", r"su ", r"chmod 777", r"chown root"],
                "risk_factors": ["系统权限修改", "可能影响系统稳定性"],
                "suggestions": ["验证命令必要性", "考虑使用最小权限"]
            },
            "network_operations": {
                "risk_level": "medium",
                "patterns": [r"curl", r"wget", r"git clone", r"pip install"],
                "risk_factors": ["网络操作可能下载恶意软件", "可能影响网络安全"],
                "suggestions": ["验证下载源可信度", "检查包签名"]
            },

            # 敏感文件风险
            "sensitive_files": {
                "risk_level": "high",
                "patterns": [
                    r"\.env$", r"\.key$", r"\.pem$", r"\.crt$",
                    r"config\.json$", r"settings\.json$"
                ],
                "risk_factors": ["敏感信息泄露风险"],
                "suggestions": ["检查是否包含机密信息", "考虑使用环境变量"]
            }
        }

    def assess_tool_call(self, tool_name: str, args: Dict[str, Any],
                        context: Dict[str, Any]) -> RiskAssessment:
        """
        评估工具调用的风险

        Args:
            tool_name: 工具名称
            args: 工具参数
            context: 调用上下文

        Returns:
            风险评估结果
        """
        risk_factors = []
        suggestions = []
        max_risk_level = "low"

        # 评估工具本身的风险
        tool_risk = self._assess_tool_risk(tool_name, args)
        if tool_risk:
            risk_factors.extend(tool_risk["risk_factors"])
            suggestions.extend(tool_risk["suggestions"])
            max_risk_level = max(max_risk_level, tool_risk["risk_level"], key=self._risk_level_value)

        # 评估参数风险
        param_risk = self._assess_parameters_risk(args)
        if param_risk:
            risk_factors.extend(param_risk["risk_factors"])
            suggestions.extend(param_risk["suggestions"])
            max_risk_level = max(max_risk_level, param_risk["risk_level"], key=self._risk_level_value)

        # 评估上下文风险
        context_risk = self._assess_context_risk(context)
        if context_risk:
            risk_factors.extend(context_risk["risk_factors"])
            suggestions.extend(context_risk["suggestions"])
            max_risk_level = max(max_risk_level, context_risk["risk_level"], key=self._risk_level_value)

        # 计算置信度
        confidence = min(0.95, 0.5 + len(risk_factors) * 0.1)

        # 确定确认级别
        confirmation_required, confirmation_level = self._determine_confirmation(max_risk_level, risk_factors)

        return RiskAssessment(
            risk_level=max_risk_level,
            confidence=confidence,
            reasons=risk_factors,
            suggestions=suggestions,
            confirmation_required=confirmation_required,
            confirmation_level=confirmation_level
        )

    def _assess_tool_risk(self, tool_name: str, args: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """评估工具本身的风险"""
        tool_lower = tool_name.lower()

        for pattern_name, pattern_config in self.risk_patterns.items():
            for pattern in pattern_config["patterns"]:
                # 检查工具名
                if re.search(pattern, tool_lower, re.IGNORECASE):
                    return pattern_config

                # 检查参数值
                for arg_value in args.values():
                    if isinstance(arg_value, str) and re.search(pattern, arg_value, re.IGNORECASE):
                        return pattern_config

        return None

    def _assess_parameters_risk(self, args: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """评估参数的风险"""
        risky_patterns = [
            (r"/etc/", "系统配置文件修改"),
            (r"/usr/", "系统目录修改"),
            (r"\.ssh/", "SSH配置修改"),
            (r"password|secret|key", "敏感信息处理"),
        ]

        risk_factors = []
        suggestions = []

        for arg_name, arg_value in args.items():
            if not isinstance(arg_value, str):
                continue

            for pattern, description in risky_patterns:
                if re.search(pattern, arg_value, re.IGNORECASE):
                    risk_factors.append(f"参数 {arg_name} 包含: {description}")
                    suggestions.append("检查参数值的合理性")

        if risk_factors:
            return {
                "risk_level": "medium" if len(risk_factors) == 1 else "high",
                "risk_factors": risk_factors,
                "suggestions": suggestions
            }

        return None

    def _assess_context_risk(self, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """评估上下文风险"""
        # 检查是否在敏感目录中操作
        cwd = context.get("cwd", "")
        sensitive_dirs = ["/etc", "/usr", "/root", "/var", "C:\\Windows", "C:\\Program Files"]

        for sensitive_dir in sensitive_dirs:
            if sensitive_dir in cwd:
                return {
                    "risk_level": "high",
                    "risk_factors": [f"在敏感目录中操作: {cwd}"],
                    "suggestions": ["确认操作必要性", "考虑使用用户目录"]
                }

        return None

    def _risk_level_value(self, level: str) -> int:
        """风险等级的数值映射"""
        mapping = {"low": 1, "medium": 2, "high": 3, "critical": 4}
        return mapping.get(level, 0)

    def _determine_confirmation(self, risk_level: str,
                              risk_factors: List[str]) -> Tuple[bool, ConfirmationLevel]:
        """确定是否需要确认及确认级别"""
        if risk_level in ["high", "critical"]:
            return True, ConfirmationLevel.STRICT
        elif risk_level == "medium" or len(risk_factors) > 1:
            return True, ConfirmationLevel.NORMAL
        elif len(risk_factors) > 0:
            return True, ConfirmationLevel.QUIET
        else:
            return False, ConfirmationLevel.NONE


class InteractiveConfirmer:
    """
    交互式确认器
    处理用户确认流程
    """

    def __init__(self, console):
        self.console = console

    def confirm_operation(self, assessment: RiskAssessment,
                         operation_description: str) -> bool:
        """
        确认操作执行

        Args:
            assessment: 风险评估结果
            operation_description: 操作描述

        Returns:
            用户是否同意执行
        """
        if not assessment.should_confirm():
            return True

        # 显示确认消息
        self.console.print(assessment.get_confirmation_message())
        self.console.print(f"\n操作: {operation_description}")
        self.console.print()

        # 根据确认级别显示不同的提示
        if assessment.confirmation_level == ConfirmationLevel.STRICT:
            prompt = "[bold red]⚠️  这是一个高风险操作，确定要继续吗？(输入 'yes' 确认): [/bold red]"
            response = self.console.input(prompt).strip().lower()
            return response == "yes"
        elif assessment.confirmation_level == ConfirmationLevel.VERBOSE:
            self.console.print("[yellow]详细风险信息:[/yellow]")
            for i, reason in enumerate(assessment.reasons, 1):
                self.console.print(f"  {i}. {reason}")
            self.console.print()
            return self._get_yes_no("是否继续？")
        else:
            return self._get_yes_no("是否继续执行此操作？")

    def _get_yes_no(self, prompt: str) -> bool:
        """获取是/否确认"""
        from rich.prompt import Confirm
        return Confirm.ask(f"[cyan]{prompt}[/cyan]", default=False)


# 全局风险评估器实例
_risk_assessor: Optional[RiskAssessor] = None
_interactive_confirmer: Optional[InteractiveConfirmer] = None

def get_risk_assessor() -> RiskAssessor:
    """获取风险评估器"""
    global _risk_assessor
    if _risk_assessor is None:
        _risk_assessor = RiskAssessor()
    return _risk_assessor

def get_interactive_confirmer(console):
    """获取交互式确认器"""
    global _interactive_confirmer
    if _interactive_confirmer is None:
        _interactive_confirmer = InteractiveConfirmer(console)
    return _interactive_confirmer