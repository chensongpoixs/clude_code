"""
业界标准的token超限处理上下文管理器
参考：OpenAI GPT-4、Claude、LangChain等业界最佳实践
"""
import tiktoken
from typing import List, Dict, Any, Optional, Tuple, Union
from dataclasses import dataclass, field
from enum import Enum

from clude_code.llm.http_client import ChatMessage


class ContextPriority(Enum):
    """上下文优先级 (业界标准排序)"""
    CRITICAL = 5  # 系统提示词 (不可丢弃)
    HIGH = 4      # 当前任务信息 (优先保留)
    MEDIUM = 3    # 最近对话历史 (可压缩)
    LOW = 2       # 旧历史信息 (可丢弃)
    TRIVIAL = 1   # 可丢弃信息 (最先丢弃)
    
    def __lt__(self, other):
        if self.__class__ is other.__class__:
            return self.value < other.value
        return NotImplemented
    
    def __gt__(self, other):
        if self.__class__ is other.__class__:
            return self.value > other.value
        return NotImplemented


@dataclass
class ContextItem:
    """上下文项"""
    content: str
    priority: ContextPriority
    category: str
    token_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=lambda: __import__('time').time())

    def calculate_tokens(self, encoding_name: str = "cl100k_base") -> int:
        """计算token数量"""
        if self.token_count > 0:
            return self.token_count

        try:
            encoding = tiktoken.get_encoding(encoding_name)
            self.token_count = len(encoding.encode(self.content))
        except Exception:
            # 简单估算
            self.token_count = len(self.content) // 2

        return self.token_count


@dataclass
class ContextWindow:
    """上下文窗口配置"""
    max_tokens: int
    reserved_tokens: int = 1000  # 为回复预留
    safety_margin: float = 0.1  # 安全边际10%

    @property
    def available_tokens(self) -> int:
        """可用token数（包含安全边际）"""
        available = max(0, self.max_tokens - self.reserved_tokens)
        result = int(available * (1 - self.safety_margin))
        # 确保至少有最小可用token
        return max(result, 100)  # 最少保留100个token


class IndustryContextManager:
    """
    业界标准的上下文管理器
    
    参考：
    1. OpenAI的上下文管理策略
    2. Anthropic Claude的压缩策略  
    3. LangChain的记忆管理
    4. Microsoft Semantic Kernel的上下文优化
    """

    def __init__(self, max_tokens: int = 4000):
        self.window = ContextWindow(max_tokens=max_tokens)
        self.context_items: List[ContextItem] = []
        self.encoding_name = "cl100k_base"
        
        # 业界标准压缩参数
        self.compression_enabled = True
        self.max_compression_attempts = 3  # 最大压缩尝试次数
        self.min_retention_ratio = {
            ContextPriority.CRITICAL: 1.0,  # 100%保留
            ContextPriority.HIGH: 0.8,     # 80%保留
            ContextPriority.MEDIUM: 0.5,    # 50%保留
            ContextPriority.LOW: 0.2,      # 20%保留
            ContextPriority.TRIVIAL: 0.0   # 0%保留
        }

    def add_message(self, message: Union[ChatMessage, str], 
                   priority: ContextPriority = ContextPriority.MEDIUM) -> None:
        """添加消息到上下文"""
        if isinstance(message, str):
            category = "user" if not message.startswith("System:") else "system"
            content = message
            original_role = category
        else:
            category = message.role
            content = self._normalize_content(message.content)
            original_role = message.role

        context_item = ContextItem(
            content=content,
            priority=priority,
            category=category,
            metadata={"original_role": original_role}
        )

        self.context_items.append(context_item)

    def add_system_context(self, content: str, 
                          priority: ContextPriority = ContextPriority.CRITICAL) -> None:
        """添加系统上下文"""
        context_item = ContextItem(
            content=content,
            priority=priority,
            category="system",
            metadata={"type": "system_prompt"}
        )
        self.context_items.insert(0, context_item)

    def optimize_context(self) -> List[ContextItem]:
        """
        优化上下文以适应token预算
        
        业界标准策略：
        1. 优先级排序
        2. 渐进式压缩
        3. 硬性截断
        """
        if not self.context_items:
            return []

        # 计算所有token
        for item in self.context_items:
            item.calculate_tokens(self.encoding_name)

        total_tokens = sum(item.token_count for item in self.context_items)
        
        # 如果在预算内，直接返回
        if total_tokens <= self.window.available_tokens:
            return self.context_items.copy()

        # 渐进式压缩策略
        return self._progressive_compression()

    def _progressive_compression(self) -> List[ContextItem]:
        """渐进式压缩（业界标准）"""
        for attempt in range(self.max_compression_attempts):
            # 按优先级分组
            priority_groups = self._group_by_priority()
            
            # 应用保留策略
            compressed_items = []
            used_tokens = 0
            
            for priority in [ContextPriority.CRITICAL, ContextPriority.HIGH, 
                           ContextPriority.MEDIUM, ContextPriority.LOW, ContextPriority.TRIVIAL]:
                if priority not in priority_groups:
                    continue
                    
                items = priority_groups[priority]
                keep_ratio = self.min_retention_ratio[priority]
                
                # 按时间排序，保留最新的
                items.sort(key=lambda x: x.created_at, reverse=True)
                
                # 计算该优先级可用的token数
                priority_budget = int(self.window.available_tokens * keep_ratio) - used_tokens
                if priority_budget <= 0:
                    continue
                
                # 选择要保留的项目
                selected_items = self._select_items_by_budget(items, priority_budget)
                
                for item in selected_items:
                    if used_tokens + item.token_count <= self.window.available_tokens:
                        compressed_items.append(item)
                        used_tokens += item.token_count
                    else:
                        # 压缩这个项目
                        compressed_item = self._compress_item(item, 
                                                           self.window.available_tokens - used_tokens)
                        if compressed_item:
                            compressed_items.append(compressed_item)
                            used_tokens += compressed_item.token_count
            
            # 检查是否满足token预算
            if used_tokens <= self.window.available_tokens:
                return compressed_items
            
            # 如果仍然超限，继续下一轮更激进的压缩
            self._increase_compression_aggressiveness(attempt)
        
        # 最后的硬性截断
        return self._hard_truncate()

    def _group_by_priority(self) -> Dict[ContextPriority, List[ContextItem]]:
        """按优先级分组"""
        groups = {}
        for item in self.context_items:
            if item.priority not in groups:
                groups[item.priority] = []
            groups[item.priority].append(item)
        return groups

    def _select_items_by_budget(self, items: List[ContextItem], 
                              budget: int) -> List[ContextItem]:
        """根据预算选择项目"""
        selected = []
        used = 0
        
        for item in items:
            if used + item.token_count <= budget:
                selected.append(item)
                used += item.token_count
        
        return selected

    def _compress_item(self, item: ContextItem, max_tokens: int) -> Optional[ContextItem]:
        """压缩单个项目"""
        if max_tokens <= 50:  # 最小保护
            return None
            
        if item.category == "system":
            # 系统消息：保留开头关键部分
            return self._compress_system_message(item, max_tokens)
        elif item.category in ("assistant", "user"):
            # 对话内容：智能截断
            return self._compress_conversation(item, max_tokens)
        elif item.category == "tool_result":
            # 工具结果：简化摘要
            return self._compress_tool_result(item, max_tokens)
        else:
            # 其他：最小化表示
            return self._compress_generic(item, max_tokens)

    def _compress_system_message(self, item: ContextItem, max_tokens: int) -> ContextItem:
        """压缩系统消息"""
        # 保留前60%的内容
        keep_chars = int(len(item.content) * 0.6)
        content = item.content[:keep_chars]
        
        if len(content) > max_tokens * 3:  # 粗略估算
            content = self._truncate_to_chars(content, max_tokens * 3)
        
        content += "\n... [系统消息已压缩]"
        
        return ContextItem(
            content=content,
            priority=item.priority,
            category="system_compressed",
            metadata={**item.metadata, "compressed": True}
        )

    def _compress_conversation(self, item: ContextItem, max_tokens: int) -> ContextItem:
        """压缩对话内容"""
        # 保留关键信息（前40% + 后20%）
        content = item.content
        if len(content) > 100:
            keep_start = int(len(content) * 0.4)
            keep_end = int(len(content) * 0.2)
            content = content[:keep_start] + "\n... [内容省略] ...\n" + content[-keep_end:]
        
        content = self._truncate_to_tokens(content, max_tokens)
        content = f"[{item.category}压缩] {content}"
        
        return ContextItem(
            content=content,
            priority=item.priority,
            category=f"{item.category}_compressed",
            metadata={**item.metadata, "compressed": True}
        )

    def _compress_tool_result(self, item: ContextItem, max_tokens: int) -> ContextItem:
        """压缩工具结果"""
        tool_name = item.metadata.get("tool_name", "unknown")
        content = f"[工具结果] {tool_name}: 执行完成，结果已压缩"
        
        return ContextItem(
            content=content,
            priority=ContextPriority.LOW,
            category="tool_result_compressed",
            metadata={**item.metadata, "compressed": True}
        )

    def _compress_generic(self, item: ContextItem, max_tokens: int) -> ContextItem:
        """通用压缩"""
        category_desc = {
            "tool_call": "工具调用",
            "tool_result_compressed": "工具结果", 
            "assistant_compressed": "助手回复",
            "user_compressed": "用户输入"
        }.get(item.category, item.category)
        
        content = f"[{category_desc}] 已处理"
        
        return ContextItem(
            content=content,
            priority=ContextPriority.TRIVIAL,
            category="compressed",
            metadata={**item.metadata, "compressed": True}
        )

    def _increase_compression_aggressiveness(self, attempt: int) -> None:
        """增加压缩激进程度"""
        # 随着尝试次数增加，减少保留比例
        reduction = 0.8 ** (attempt + 1)  # 80%, 64%, 51%
        
        for priority in self.min_retention_ratio:
            if priority != ContextPriority.CRITICAL:
                self.min_retention_ratio[priority] *= reduction

    def _hard_truncate(self) -> List[ContextItem]:
        """硬性截断（最后手段）"""
        # 严格按优先级和时间排序
        sorted_items = sorted(self.context_items, 
                            key=lambda x: (-x.priority.value, -x.created_at))
        
        result = []
        used_tokens = 0
        
        for item in sorted_items:
            if used_tokens >= self.window.available_tokens:
                break
                
            # 强制压缩到可用空间
            remaining = self.window.available_tokens - used_tokens
            if item.token_count > remaining:
                # 创建最小化的占位符
                content = f"[{item.category}] 已截断"
                compressed_item = ContextItem(
                    content=content,
                    priority=ContextPriority.TRIVIAL,
                    category="truncated",
                    metadata={"original_category": item.category}
                )
                compressed_item.calculate_tokens(self.encoding_name)
                if used_tokens + compressed_item.token_count <= self.window.available_tokens:
                    result.append(compressed_item)
                    used_tokens += compressed_item.token_count
            else:
                result.append(item)
                used_tokens += item.token_count
        
        return result

    def _normalize_content(self, content: Union[str, List]) -> str:
        """标准化多模态内容"""
        if isinstance(content, str):
            return content
        elif isinstance(content, list):
            # 提取文本内容
            text_parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_parts.append(item.get("text", ""))
                elif isinstance(item, str):
                    text_parts.append(item)
            return "\n".join(text_parts)
        else:
            return str(content)

    def _truncate_to_chars(self, content: str, max_chars: int) -> str:
        """按字符数截断"""
        if len(content) <= max_chars:
            return content
        return content[:max_chars] + "... [截断]"

    def _truncate_to_tokens(self, content: str, max_tokens: int) -> str:
        """按token数截断"""
        try:
            encoding = tiktoken.get_encoding(self.encoding_name)
            tokens = encoding.encode(content)
            if len(tokens) <= max_tokens:
                return content
            truncated_tokens = tokens[:max_tokens]
            return encoding.decode(truncated_tokens) + "... [token截断]"
        except Exception:
            # 降级到字符截断
            return self._truncate_to_chars(content, max_tokens * 3)

    def clear_context(self, keep_system: bool = True) -> None:
        """清空上下文"""
        if keep_system:
            system_items = [item for item in self.context_items if item.category == "system"]
            self.context_items = system_items
        else:
            self.context_items.clear()

    def get_context_stats(self) -> Dict[str, Any]:
        """获取上下文统计"""
        if not self.context_items:
            return {"total_items": 0, "total_tokens": 0}

        total_tokens = sum(item.calculate_tokens(self.encoding_name) 
                          for item in self.context_items)
        
        categories = {}
        for item in self.context_items:
            categories[item.category] = categories.get(item.category, 0) + 1

        return {
            "total_items": len(self.context_items),
            "total_tokens": total_tokens,
            "available_tokens": self.window.available_tokens,
            "utilization_rate": total_tokens / self.window.max_tokens,
            "categories": categories,
            "compression_enabled": self.compression_enabled
        }


# 全局实例
_industry_manager: Optional[IndustryContextManager] = None

def get_industry_context_manager(max_tokens: int = 4000) -> IndustryContextManager:
    """获取业界标准上下文管理器"""
    global _industry_manager
    if _industry_manager is None:
        _industry_manager = IndustryContextManager(max_tokens=max_tokens)
    return _industry_manager