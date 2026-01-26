"""
Claude Code标准保护机制模块

实现多层级的智能保护策略，确保关键内容不会被错误压缩
"""
from typing import List, Dict, Any, Optional, Set, Tuple
import time
from enum import Enum

from ...llm.http_client import ChatMessage
from ..core.constants import (
    ContextPriority,
    ClaudeContextItem, 
    ProtectionInfo
    ClaudeCodeConstants
)


class ProtectionLevel(Enum):
    """保护级别"""
    CRITICAL = 5    # 绝对保护（系统消息）
    HIGH = 4         # 高级保护（最近5轮）
    MEDIUM = 3       # 中级保护（当前工作）
    LOW = 2          # 低级保护（相关历史）
    TEMPORARY = 1     # 临时保护（用户指定的重要信息）
    
    def __gt__(self, other):
        if self.__class__ is other.__class__:
            return self.value > other.value
        return NotImplemented
    
    def __lt__(self, other):
        if self.__class__ is other.__class__:
            return self.value < other.value
        return NotImplemented


class ProtectionRule:
    """保护规则"""
    
    def __init__(self, name: str, condition: callable, level: ProtectionLevel, 
                 reason: str, expires_in: int = 0):
        self.name = name
        self.condition = condition
        self.level = level
        self.reason = reason
        self.expires_in = expires_in  # 秒后过期，0表示永不过期
        self.created_at = time.time()
    
    def should_protect(self, item: ClaudeContextItem, context_items: List[ClaudeContextItem]) -> bool:
        """判断是否应该保护该项"""
        return self.condition(item, context_items)
    
    def is_expired(self) -> bool:
        """检查规则是否过期"""
        if self.expires_in == 0:
            return False
        return time.time() - self.created_at > self.expires_in
    
    def get_protection_info(self, item: ClaudeContextItem) -> ProtectionInfo:
        """获取保护信息"""
        return ProtectionInfo(
            is_protected=True,
            protection_reason=self.reason,
            protection_level=self.level.value,
            expires_at=time.time() + self.expires_in if self.expires_in > 0 else 0
        )


class ProtectionEngine:
    """保护引擎
    
    实现多种保护策略：
    1. 优先级保护：根据ContextPriority自动保护
    2. 规则保护：基于自定义规则的保护
    3. 时间保护：临时保护重要信息
    4. 用户保护：用户明确指定的保护
    5. 动态保护：基于使用模式的自适应保护
    """
    
    def __init__(self):
        self.protection_rules: List[ProtectionRule] = []
        self.user_protected_items: Set[str] = set()
        self.temp_protection: Dict[str, ProtectionInfo] = {}
        self.protection_stats: Dict[str, Any] = {
            "total_protections": 0,
            "rule_matches": {},
            "user_protections": 0,
            "temp_protections": 0,
            "auto_protections": 0
        }
        
        # 初始化内置保护规则
        self._initialize_default_rules()
    
    def _initialize_default_rules(self) -> None:
        """初始化默认保护规则"""
        
        # 规则1：系统消息绝对保护
        self.add_rule(ProtectionRule(
            name="system_message_protection",
            condition=lambda item, ctx: item.category == "system",
            level=ProtectionLevel.CRITICAL,
            reason="系统提示词，永不丢弃",
            expires_in=0  # 永不过期
        ))
        
        # 规则2：最近5轮对话高保护
        self.add_rule(ProtectionRule(
            name="recent_conversation_protection", 
            condition=lambda item, ctx: self._is_recent_conversation(item, ctx),
            level=ProtectionLevel.HIGH,
            reason="最近5轮对话，高优先级",
            expires_in=0
        ))
        
        # 规则3：当前工作记忆中等保护
        self.add_rule(ProtectionRule(
            name="current_working_memory",
            condition=lambda item, ctx: self._is_current_working_memory(item, ctx),
            level=ProtectionLevel.MEDIUM,
            reason="当前工作记忆，中等优先级",
            expires_in=ClaudeCodeConstants.PROTECTED_ROUNDS * 60  # 5轮对话时长
        ))
        
        # 规则4：重要用户信息临时保护
        self.add_rule(ProtectionRule(
            name="important_user_info",
            condition=lambda item, ctx: self._contains_important_info(item),
            level=ProtectionLevel.TEMPORARY,
            reason="包含重要用户信息，临时保护",
            expires_in=300  # 5分钟临时保护
        ))
        
        # 规则5：工具调用上下文保护
        self.add_rule(ProtectionRule(
            name="tool_call_context_protection",
            condition=lambda item, ctx: self._is_tool_call_context(item, ctx),
            level=ProtectionLevel.MEDIUM,
            reason="工具调用上下文，需要保持连贯",
            expires_in=180  # 3分钟保护
        ))
    
    def _is_recent_conversation(self, item: ClaudeContextItem, 
                             context_items: List[ClaudeContextItem]) -> bool:
        """判断是否为最近对话"""
        if item.category not in ["user", "assistant"]:
            return False
        
        # 统计最近的user/assistant消息
        recent_messages = []
        for ctx_item in context_items:
            if ctx_item.category in ["user", "assistant"]:
                recent_messages.append(ctx_item)
        
        # 如果该项目在最近的10条消息中，则认为是最近的
        recent_messages.sort(key=lambda x: x.created_at, reverse=True)
        recent_ids = set(id(item) for item in recent_messages[:10])
        
        return id(item) in recent_ids
    
    def _is_current_working_memory(self, item: ClaudeContextItem, 
                                 context_items: List[ClaudeContextItem]) -> bool:
        """判断是否为当前工作记忆"""
        # 当前工作记忆的标准：
        # 1. 优先级为WORKING
        # 2. 时间在最近3轮对话中
        # 3. 内容长度适中（不是过长或过短）
        
        if item.priority != ContextPriority.WORKING:
            return False
        
        # 检查是否在最近对话中
        if not self._is_recent_conversation(item, context_items):
            return False
        
        # 检查内容长度
        content_length = len(item.content)
        if content_length < 10 or content_length > 1000:
            return False
        
        return True
    
    def _contains_important_info(self, item: ClaudeContextItem) -> bool:
        """判断是否包含重要信息"""
        content = item.content.lower()
        
        # 重要信息关键词
        important_keywords = [
            "密码", "password", "密钥", "key", "token",
            "重要", "important", "记住", "remember", "不要忘记",
            "注意", "attention", "警告", "warning",
            "错误", "error", "bug", "问题", "problem"
        ]
        
        return any(keyword in content for keyword in important_keywords)
    
    def _is_tool_call_context(self, item: ClaudeContextItem, 
                            context_items: List[ClaudeContextItem]) -> bool:
        """判断是否为工具调用上下文"""
        if item.category != "tool_result":
            return False
        
        # 检查最近的工具调用
        for ctx_item in context_items:
            if ctx_item.category == "tool_call":
                # 如果工具调用结果在工具调用之后，则认为是上下文
                if ctx_item.created_at < item.created_at:
                    return True
        
        return False
    
    def add_rule(self, rule: ProtectionRule) -> None:
        """添加保护规则"""
        self.protection_rules.append(rule)
        self.protection_stats["rule_matches"][rule.name] = 0
    
    def remove_rule(self, rule_name: str) -> bool:
        """移除保护规则"""
        for i, rule in enumerate(self.protection_rules):
            if rule.name == rule_name:
                del self.protection_rules[i]
                return True
        return False
    
    def add_user_protection(self, item_id: str, expires_in: int = 600) -> None:
        """添加用户保护"""
        self.user_protected_items.add(item_id)
        self.protection_stats["user_protections"] += 1
        
        # 设置过期时间
        if expires_in > 0:
            # 在实际实现中，这里应该设置定时器清理
            pass
    
    def remove_user_protection(self, item_id: str) -> bool:
        """移除用户保护"""
        if item_id in self.user_protected_items:
            self.user_protected_items.remove(item_id)
            return True
        return False
    
    def add_temp_protection(self, key: str, level: ProtectionLevel, 
                          reason: str, expires_in: int) -> None:
        """添加临时保护"""
        self.temp_protection[key] = ProtectionInfo(
            is_protected=True,
            protection_reason=reason,
            protection_level=level.value,
            expires_at=time.time() + expires_in
        )
        self.protection_stats["temp_protections"] += 1
    
    def should_protect_item(self, item: ClaudeContextItem, 
                            context_items: List[ClaudeContextItem]) -> Tuple[bool, ProtectionInfo]:
        """判断项目是否应该被保护"""
        # 检查临时保护
        item_key = self._get_item_key(item)
        if item_key in self.temp_protection:
            protection_info = self.temp_protection[item_key]
            if time.time() < protection_info.expires_at:
                self.protection_stats["auto_protections"] += 1
                return True, protection_info
            else:
                # 过期，清理临时保护
                del self.temp_protection[item_key]
        
        # 检查用户保护
        if item_key in self.user_protected_items:
            self.protection_stats["auto_protections"] += 1
            return True, ProtectionInfo(
                is_protected=True,
                protection_reason="用户指定保护",
                protection_level=ProtectionLevel.HIGH.value,
                expires_at=0
            )
        
        # 检查规则保护
        for rule in self.protection_rules:
            if rule.is_expired():
                continue
            
            if rule.should_protect(item, context_items):
                self.protection_stats["rule_matches"][rule.name] += 1
                return True, rule.get_protection_info(item)
        
        # 基于优先级的自动保护
        auto_protection = self._get_priority_protection(item)
        if auto_protection:
            self.protection_stats["auto_protections"] += 1
            return True, auto_protection
        
        return False, ProtectionInfo()
    
    def _get_item_key(self, item: ClaudeContextItem) -> str:
        """获取项目唯一标识"""
        # 基于内容和时间戳生成唯一标识
        import hashlib
        content_hash = hashlib.md5(item.content.encode()).hexdigest()[:8]
        return f"{item.category}_{item.created_at}_{content_hash}"
    
    def _get_priority_protection(self, item: ClaudeContextItem) -> Optional[ProtectionInfo]:
        """获取基于优先级的保护信息"""
        if item.priority == ContextPriority.PROTECTED:
            return ProtectionInfo(
                is_protected=True,
                protection_reason="系统优先级保护",
                protection_level=ProtectionLevel.CRITICAL.value,
                expires_at=0
            )
        elif item.priority == ContextPriority.RECENT:
            return ProtectionInfo(
                is_protected=True,
                protection_reason="最近对话保护",
                protection_level=ProtectionLevel.HIGH.value,
                expires_at=0
            )
        elif item.priority == ContextPriority.WORKING:
            return ProtectionInfo(
                is_protected=True,
                protection_reason="工作记忆保护",
                protection_level=ProtectionLevel.MEDIUM.value,
                expires_at=0
            )
        
        return None
    
    def evaluate_protection_coverage(self, context_items: List[ClaudeContextItem]) -> Dict[str, Any]:
        """评估保护覆盖率"""
        if not context_items:
            return {"coverage_rate": 0.0, "protected_count": 0, "total_count": 0}
        
        protected_count = 0
        total_count = len(context_items)
        
        for item in context_items:
            should_protect, _ = self.should_protect_item(item, context_items)
            if should_protect:
                protected_count += 1
        
        coverage_rate = protected_count / max(1, total_count)
        
        return {
            "coverage_rate": coverage_rate,
            "protected_count": protected_count,
            "total_count": total_count,
            "protection_stats": self.protection_stats,
            "rule_effectiveness": self._evaluate_rule_effectiveness(),
            "protection_balance": self._evaluate_protection_balance()
        }
    
    def _evaluate_rule_effectiveness(self) -> Dict[str, Any]:
        """评估规则有效性"""
        total_matches = sum(self.protection_stats["rule_matches"].values())
        
        # 评估每个规则的匹配率
        rule_effectiveness = {}
        for rule_name, match_count in self.protection_stats["rule_matches"].items():
            rule_effectiveness[rule_name] = {
                "match_count": match_count,
                "effectiveness": "high" if match_count > 5 else "medium" if match_count > 2 else "low"
            }
        
        return rule_effectiveness
    
    def _evaluate_protection_balance(self) -> Dict[str, Any]:
        """评估保护平衡性"""
        auto_protections = self.protection_stats["auto_protections"]
        user_protections = self.protection_stats["user_protections"]
        temp_protections = self.protection_stats["temp_protections"]
        
        return {
            "auto_protection_ratio": auto_protections / max(1, auto_protections + user_protections + temp_protections),
            "user_protection_ratio": user_protections / max(1, auto_protections + user_protections + temp_protections),
            "temp_protection_ratio": temp_protections / max(1, auto_protections + user_protections + temp_protections),
            "protection_diversity": len(set([auto_protections > 0, user_protections > 0, temp_protections > 0]))
        }
    
    def get_protection_summary(self) -> Dict[str, Any]:
        """获取保护摘要"""
        return {
            "total_rules": len(self.protection_rules),
            "active_rules": len([r for r in self.protection_rules if not r.is_expired()]),
            "user_protected_items": len(self.user_protected_items),
            "temp_protections": len(self.temp_protection),
            "protection_stats": self.protection_stats,
            "recommendations": self._generate_recommendations()
        }
    
    def _generate_recommendations(self) -> List[str]:
        """生成保护建议"""
        recommendations = []
        
        # 基于统计数据的建议
        if self.protection_stats["auto_protections"] > 100:
            recommendations.append("考虑增加更多自动保护规则以减少手动操作")
        
        if self.protection_stats["user_protections"] > 50:
            recommendations.append("用户保护使用频繁，考虑提供批量管理功能")
        
        if len(self.temp_protection) > 20:
            recommendations.append("临时保护项目较多，考虑减少临时保护的使用")
        
        # 基于规则有效性的建议
        ineffective_rules = [name for name, stats in self.protection_stats["rule_matches"].items() 
                           if stats["effectiveness"] == "low"]
        if ineffective_rules:
            recommendations.append(f"考虑优化或移除低效规则: {', '.join(ineffective_rules)}")
        
        return recommendations


# 全局保护引擎实例
_protection_engine: Optional[ProtectionEngine] = None

def get_protection_engine() -> ProtectionEngine:
    """获取保护引擎实例"""
    global _protection_engine
    if _protection_engine is None:
        _protection_engine = ProtectionEngine()
    return _protection_engine