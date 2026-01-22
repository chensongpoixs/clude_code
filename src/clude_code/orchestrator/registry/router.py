"""
Intent Router - 意图路由器

功能：
- 根据用户输入匹配最合适的意图
- 支持关键词匹配（精确/模糊）
- 优先使用 Intent Registry，无匹配时回退到 IntentClassifier

路由优先级：
1. 精确关键词匹配（keywords 包含完整词）
2. 模糊关键词匹配（keywords 部分匹配）
3. IntentClassifier（LLM 意图分类）
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional, Callable, Any

from clude_code.orchestrator.registry.schema import IntentSpec, RiskLevel
from clude_code.orchestrator.registry.loader import IntentRegistry


_logger = logging.getLogger(__name__)


@dataclass
class IntentMatch:
    """
    意图匹配结果。
    
    Attributes:
        intent: 匹配到的意图配置（如果有）
        source: 匹配来源：registry / classifier / default
        confidence: 置信度（0.0 ~ 1.0）
        matched_keywords: 匹配的关键词列表
        reason: 匹配原因说明
    """
    intent: Optional[IntentSpec]
    source: str
    confidence: float
    matched_keywords: list[str]
    reason: str
    
    # 便捷属性
    @property
    def name(self) -> str:
        return self.intent.name if self.intent else "default"
    
    @property
    def risk_level(self) -> RiskLevel:
        return self.intent.risk_level if self.intent else RiskLevel.MEDIUM
    
    @property
    def mode(self) -> str:
        return self.intent.mode if self.intent else "unified"
    
    @property
    def tools(self) -> list[str]:
        return self.intent.tools if self.intent else []
    
    @property
    def prompt_ref(self) -> Optional[str]:
        return self.intent.prompt_ref if self.intent else None

    @property
    def prompts(self):
        return getattr(self.intent, "prompts", None) if self.intent else None


class IntentRouter:
    """
    意图路由器。
    
    根据用户输入选择最合适的意图配置。
    
    使用示例：
        registry = IntentRegistry(workspace_root)
        router = IntentRouter(registry)
        match = router.route("帮我审查这段代码")
        print(match.name, match.risk_level, match.tools)
    """
    
    def __init__(
        self,
        registry: IntentRegistry,
        *,
        fallback_classifier: Optional[Callable[[str], tuple[str, float]]] = None,
    ) -> None:
        """
        初始化路由器。
        
        Args:
            registry: IntentRegistry 实例
            fallback_classifier: 回退分类器函数（接收 user_text，返回 (intent_name, confidence)）
        """
        self._registry = registry
        self._fallback_classifier = fallback_classifier
    
    def route(
        self,
        user_text: str,
        *,
        project_id: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> IntentMatch:
        """
        路由用户输入到最合适的意图。
        
        Args:
            user_text: 用户输入文本
            project_id: 项目 ID（用于项目级配置覆盖）
            context: 上下文信息（预留扩展）
            
        Returns:
            IntentMatch 结果
        """
        user_text_lower = user_text.lower().strip()
        
        # 1. 尝试从 Registry 匹配
        config = self._registry.get_config()
        intents = [i for i in config.intents if i.enabled]
        
        if intents:
            # 按优先级排序
            intents_sorted = sorted(intents, key=lambda x: -x.priority)
            
            # 精确匹配
            for intent in intents_sorted:
                matched = self._match_keywords(user_text_lower, intent.keywords, exact=True)
                if matched:
                    _logger.info(f"[IntentRouter] 精确匹配: {intent.name}, keywords={matched}")
                    return IntentMatch(
                        intent=intent,
                        source="registry",
                        confidence=1.0,
                        matched_keywords=matched,
                        reason=f"精确关键词匹配: {matched}",
                    )
            
            # 模糊匹配
            best_match: Optional[tuple[IntentSpec, list[str], float]] = None
            for intent in intents_sorted:
                matched = self._match_keywords(user_text_lower, intent.keywords, exact=False)
                if matched:
                    score = len(matched) / max(len(intent.keywords), 1)
                    if best_match is None or score > best_match[2]:
                        best_match = (intent, matched, score)
            
            if best_match and best_match[2] >= 0.3:  # 至少 30% 匹配
                intent, matched, score = best_match
                _logger.info(f"[IntentRouter] 模糊匹配: {intent.name}, score={score:.2f}, keywords={matched}")
                return IntentMatch(
                    intent=intent,
                    source="registry",
                    confidence=min(0.5 + score * 0.5, 0.9),  # 0.5 ~ 0.9
                    matched_keywords=matched,
                    reason=f"模糊关键词匹配: {matched} (score={score:.2f})",
                )
        
        # 2. 回退到 Classifier
        if self._fallback_classifier:
            try:
                intent_name, confidence = self._fallback_classifier(user_text)
                _logger.info(f"[IntentRouter] Classifier 分类: {intent_name}, confidence={confidence:.2f}")
                # 尝试在 Registry 中找到对应的 IntentSpec
                intent_spec = config.get_intent_by_name(intent_name) if config else None
                return IntentMatch(
                    intent=intent_spec,
                    source="classifier",
                    confidence=confidence,
                    matched_keywords=[],
                    reason=f"LLM 意图分类: {intent_name}",
                )
            except Exception as e:
                _logger.warning(f"[IntentRouter] Classifier 失败: {e}")
        
        # 3. 默认意图
        _logger.debug(f"[IntentRouter] 无匹配，使用默认意图")
        return IntentMatch(
            intent=None,
            source="default",
            confidence=0.0,
            matched_keywords=[],
            reason="无匹配，使用默认配置",
        )
    
    def _match_keywords(
        self,
        text: str,
        keywords: list[str],
        *,
        exact: bool = False,
    ) -> list[str]:
        """
        匹配关键词。
        
        Args:
            text: 用户输入（已小写）
            keywords: 关键词列表
            exact: 是否精确匹配（整词匹配）
            
        Returns:
            匹配到的关键词列表
        """
        matched = []
        for kw in keywords:
            kw_lower = kw.lower()
            if exact:
                # 判断是否为纯 ASCII（英文）
                is_ascii = all(ord(c) < 128 for c in kw_lower.replace(' ', ''))
                if is_ascii:
                    # 英文：整词边界匹配
                    pattern = r'\b' + re.escape(kw_lower) + r'\b'
                    if re.search(pattern, text):
                        matched.append(kw)
                else:
                    # 中文/非 ASCII：包含即可（中文没有词边界概念）
                    if kw_lower in text:
                        matched.append(kw)
            else:
                # 模糊匹配：包含即可
                if kw_lower in text:
                    matched.append(kw)
        return matched
    
    def get_tools_for_intent(self, intent_name: str) -> list[str]:
        """获取意图允许的工具列表。"""
        intent = self._registry.get_intent(intent_name)
        return intent.tools if intent else []

