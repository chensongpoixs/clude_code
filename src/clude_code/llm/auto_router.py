"""
自动路由模块（Auto Router）

功能：
1. 根据任务类型自动选择最合适的模型
2. 考虑因素：成本、速度、能力（Vision/Code）
3. 支持用户偏好覆盖

设计原则：
- 可配置的路由策略
- 支持动态调整
- 透明的决策过程
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .base import ModelInfo

logger = logging.getLogger(__name__)


class TaskType(Enum):
    """任务类型"""
    CODING = "coding"           # 代码生成/修改
    CODE_REVIEW = "code_review" # 代码审查
    DEBUGGING = "debugging"     # 调试/错误分析
    REASONING = "reasoning"     # 复杂推理
    CHAT = "chat"               # 一般对话
    SUMMARIZE = "summarize"     # 总结/摘要
    TRANSLATE = "translate"     # 翻译
    VISION = "vision"           # 图片分析
    LONG_CONTEXT = "long_context"  # 长文档处理
    FAST_RESPONSE = "fast_response"  # 快速响应


class Priority(Enum):
    """优先级"""
    COST = "cost"           # 成本优先
    SPEED = "speed"         # 速度优先
    QUALITY = "quality"     # 质量优先
    BALANCED = "balanced"   # 平衡


@dataclass
class RoutingRule:
    """路由规则"""
    task_type: TaskType
    priority: Priority
    recommended_providers: list[str]
    recommended_models: list[str]
    min_context_window: int = 0
    requires_vision: bool = False
    requires_function_call: bool = False


@dataclass
class RoutingDecision:
    """路由决策"""
    provider_id: str
    model_id: str
    reason: str
    score: float
    alternatives: list[tuple[str, str, float]] = field(default_factory=list)


# 预定义路由规则
DEFAULT_ROUTING_RULES: list[RoutingRule] = [
    # 代码生成
    RoutingRule(
        task_type=TaskType.CODING,
        priority=Priority.QUALITY,
        recommended_providers=["deepseek", "openai", "anthropic"],
        recommended_models=[
            "deepseek-coder", "deepseek-chat",
            "gpt-4o", "claude-3-5-sonnet-latest",
        ],
        requires_function_call=True,
    ),
    # 复杂推理
    RoutingRule(
        task_type=TaskType.REASONING,
        priority=Priority.QUALITY,
        recommended_providers=["openai", "deepseek", "anthropic"],
        recommended_models=[
            "o1-preview", "o1-mini", "deepseek-reasoner",
            "claude-3-opus-latest",
        ],
    ),
    # 图片分析
    RoutingRule(
        task_type=TaskType.VISION,
        priority=Priority.QUALITY,
        recommended_providers=["openai", "anthropic", "google_gemini"],
        recommended_models=[
            "gpt-4o", "gpt-4o-mini",
            "claude-3-5-sonnet-latest",
            "gemini-1.5-pro", "gemini-2.0-flash-exp",
        ],
        requires_vision=True,
    ),
    # 长文档
    RoutingRule(
        task_type=TaskType.LONG_CONTEXT,
        priority=Priority.QUALITY,
        recommended_providers=["anthropic", "google_gemini", "moonshot"],
        recommended_models=[
            "claude-3-5-sonnet-latest",  # 200K
            "gemini-1.5-pro",  # 2M
            "moonshot-v1-128k",  # 128K
        ],
        min_context_window=100000,
    ),
    # 快速响应
    RoutingRule(
        task_type=TaskType.FAST_RESPONSE,
        priority=Priority.SPEED,
        recommended_providers=["groq", "deepseek", "openai"],
        recommended_models=[
            "llama-3.3-70b-versatile",  # Groq 超快
            "deepseek-chat",
            "gpt-4o-mini",
        ],
    ),
    # 一般对话（成本优先）
    RoutingRule(
        task_type=TaskType.CHAT,
        priority=Priority.COST,
        recommended_providers=["deepseek", "qianwen", "zhipu"],
        recommended_models=[
            "deepseek-chat",
            "qwen-turbo",
            "glm-4-flash",
        ],
    ),
]


class AutoRouter:
    """
    自动路由器
    
    用法：
        router = AutoRouter()
        decision = router.route(
            task_type=TaskType.CODING,
            context_length=5000,
            has_image=False,
            available_providers=["deepseek", "openai"],
        )
        print(f"推荐: {decision.provider_id}/{decision.model_id}")
    """
    
    def __init__(
        self,
        rules: list[RoutingRule] | None = None,
        default_priority: Priority = Priority.BALANCED,
    ):
        self.rules = rules or DEFAULT_ROUTING_RULES
        self.default_priority = default_priority
        self._user_preferences: dict[str, Any] = {}
    
    def set_preference(self, key: str, value: Any) -> None:
        """设置用户偏好"""
        self._user_preferences[key] = value
    
    def get_rule(self, task_type: TaskType) -> RoutingRule | None:
        """获取指定任务类型的规则"""
        for rule in self.rules:
            if rule.task_type == task_type:
                return rule
        return None
    
    def _score_model(
        self,
        provider_id: str,
        model_id: str,
        rule: RoutingRule,
        context_length: int,
        has_image: bool,
        available_models: list["ModelInfo"] | None,
    ) -> float:
        """计算模型得分"""
        score = 0.0
        
        # 基础分：是否在推荐列表
        if model_id in rule.recommended_models:
            score += 50.0
        if provider_id in rule.recommended_providers:
            score += 30.0
        
        # 能力匹配
        model_info = None
        if available_models:
            for m in available_models:
                if m.id == model_id:
                    model_info = m
                    break
        
        if model_info:
            # Vision 需求
            if rule.requires_vision:
                if model_info.supports_vision:
                    score += 20.0
                else:
                    score -= 100.0  # 不满足硬性要求
            
            # Function Call 需求
            if rule.requires_function_call:
                if model_info.supports_function_call:
                    score += 10.0
            
            # 上下文窗口
            if rule.min_context_window > 0:
                if model_info.context_window >= rule.min_context_window:
                    score += 15.0
                else:
                    score -= 50.0  # 不满足上下文要求
            
            # 当前上下文是否超出
            if context_length > 0 and model_info.context_window < context_length:
                score -= 100.0  # 上下文不够
        
        # 优先级调整
        if rule.priority == Priority.COST:
            # 成本优先：偏好国内/免费厂商
            if provider_id in ["deepseek", "qianwen", "zhipu", "ollama", "openai_compat"]:
                score += 15.0
        elif rule.priority == Priority.SPEED:
            # 速度优先：偏好 Groq 等快速推理
            if provider_id == "groq":
                score += 20.0
        elif rule.priority == Priority.QUALITY:
            # 质量优先：偏好顶级模型
            if model_id in ["gpt-4o", "claude-3-5-sonnet-latest", "o1-preview"]:
                score += 15.0
        
        # 用户偏好
        preferred_provider = self._user_preferences.get("preferred_provider")
        if preferred_provider and provider_id == preferred_provider:
            score += 25.0
        
        return score
    
    def route(
        self,
        task_type: TaskType,
        context_length: int = 0,
        has_image: bool = False,
        available_providers: list[str] | None = None,
        available_models: list["ModelInfo"] | None = None,
    ) -> RoutingDecision:
        """
        执行路由决策。
        
        Args:
            task_type: 任务类型
            context_length: 上下文长度
            has_image: 是否包含图片
            available_providers: 可用厂商列表
            available_models: 可用模型列表
        
        Returns:
            路由决策
        """
        rule = self.get_rule(task_type)
        if not rule:
            # 默认规则
            rule = RoutingRule(
                task_type=task_type,
                priority=self.default_priority,
                recommended_providers=["deepseek", "openai"],
                recommended_models=["deepseek-chat", "gpt-4o"],
            )
        
        # 强制 Vision 需求
        if has_image:
            rule = RoutingRule(
                task_type=rule.task_type,
                priority=rule.priority,
                recommended_providers=["openai", "anthropic", "google_gemini"],
                recommended_models=["gpt-4o", "claude-3-5-sonnet-latest", "gemini-1.5-pro"],
                requires_vision=True,
            )
        
        # 收集候选
        candidates: list[tuple[str, str, float]] = []
        
        for provider_id in (available_providers or rule.recommended_providers):
            for model_id in rule.recommended_models:
                score = self._score_model(
                    provider_id, model_id, rule, context_length, has_image, available_models
                )
                if score > 0:
                    candidates.append((provider_id, model_id, score))
        
        # 排序
        candidates.sort(key=lambda x: x[2], reverse=True)
        
        if not candidates:
            # 兜底
            return RoutingDecision(
                provider_id="deepseek",
                model_id="deepseek-chat",
                reason="无匹配候选，使用默认模型",
                score=0.0,
            )
        
        best = candidates[0]
        return RoutingDecision(
            provider_id=best[0],
            model_id=best[1],
            reason=f"任务类型={task_type.value}, 优先级={rule.priority.value}",
            score=best[2],
            alternatives=candidates[1:5],  # 前 5 个备选
        )
    
    def detect_task_type(self, user_input: str) -> TaskType:
        """
        从用户输入检测任务类型（简单规则匹配）。
        
        注意：这是简化实现，实际应用可用 LLM 分类。
        """
        input_lower = user_input.lower()
        
        # 图片相关
        if any(kw in input_lower for kw in ["图片", "image", "screenshot", "截图", "看看", "分析图"]):
            return TaskType.VISION
        
        # 代码相关
        if any(kw in input_lower for kw in ["代码", "code", "实现", "function", "class", "编写", "修改"]):
            return TaskType.CODING
        
        # 调试相关
        if any(kw in input_lower for kw in ["错误", "error", "bug", "调试", "debug", "fix"]):
            return TaskType.DEBUGGING
        
        # 推理相关
        if any(kw in input_lower for kw in ["推理", "reason", "分析", "为什么", "explain"]):
            return TaskType.REASONING
        
        # 总结
        if any(kw in input_lower for kw in ["总结", "summarize", "摘要", "概括"]):
            return TaskType.SUMMARIZE
        
        # 翻译
        if any(kw in input_lower for kw in ["翻译", "translate", "英译中", "中译英"]):
            return TaskType.TRANSLATE
        
        # 默认对话
        return TaskType.CHAT


# ============================================================
# 便捷函数
# ============================================================

_global_router: AutoRouter | None = None


def get_auto_router() -> AutoRouter:
    """获取全局路由器"""
    global _global_router
    if _global_router is None:
        _global_router = AutoRouter()
    return _global_router


def auto_select_model(
    task_type: TaskType | str,
    context_length: int = 0,
    has_image: bool = False,
    available_providers: list[str] | None = None,
) -> RoutingDecision:
    """便捷函数：自动选择模型"""
    if isinstance(task_type, str):
        task_type = TaskType(task_type)
    return get_auto_router().route(
        task_type=task_type,
        context_length=context_length,
        has_image=has_image,
        available_providers=available_providers,
    )

