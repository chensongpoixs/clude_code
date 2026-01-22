"""
高级上下文管理器
参考Claude Code，实现智能的token预算管理和上下文优化
"""
try:
    import tiktoken  # type: ignore
except Exception:  # optional dependency
    tiktoken = None  # type: ignore
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

from clude_code.llm.llama_cpp_http import ChatMessage


class ContextPriority(Enum):
    """上下文优先级"""
    CRITICAL = 5  # 系统提示词、核心指令
    HIGH = 4      # 当前任务相关信息
    MEDIUM = 3    # 最近的对话历史
    LOW = 2       # 旧的历史信息
    TRIVIAL = 1   # 可以丢弃的信息


@dataclass
class ContextItem:
    """上下文项"""
    content: str
    priority: ContextPriority
    category: str  # system, user, assistant, tool, etc.
    token_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=lambda: __import__('time').time())

    def calculate_tokens(self, encoding_name: str = "cl100k_base") -> int:
        """计算token数量"""
        if self.token_count > 0:
            return self.token_count

        try:
            if tiktoken is None:
                raise RuntimeError("tiktoken_missing")
            encoding = tiktoken.get_encoding(encoding_name)
            self.token_count = len(encoding.encode(self.content))
        except Exception:
            # 简单估算：1个中文字符≈1.5个token，英文单词≈1个token
            self.token_count = len(self.content) // 2  # 粗略估算

        return self.token_count


@dataclass
class ContextWindow:
    """上下文窗口配置"""
    max_tokens: int
    reserved_tokens: int = 1000  # 为回复预留的token数
    min_context_tokens: int = 500  # 最少保留的上下文token数

    @property
    def available_tokens(self) -> int:
        """可用token数"""
        return max(0, self.max_tokens - self.reserved_tokens)


class AdvancedContextManager:
    """
    高级上下文管理器
    实现智能的token预算管理和内容优化
    """

    def __init__(self, max_tokens: int = 4000):
        self.window = ContextWindow(max_tokens=max_tokens)
        self.context_items: List[ContextItem] = []
        self.encoding_name = "cl100k_base"  # GPT-4的编码

        # 压缩策略
        self.compression_enabled = True
        self.compression_threshold = 0.8  # 当使用率超过80%时开始压缩

    def add_message(self, message: ChatMessage, priority: ContextPriority = ContextPriority.MEDIUM) -> None:
        """添加消息到上下文"""
        category = message.role
        content = message.content or ""

        # 处理工具调用结果
        if hasattr(message, 'tool_calls') and message.tool_calls:
            category = "tool_call"
            # 简化工具调用显示
            tool_info = f"调用工具: {len(message.tool_calls)}个工具"
            content = f"{tool_info}\n{self._summarize_tool_calls(message.tool_calls)}"

        context_item = ContextItem(
            content=content,
            priority=priority,
            category=category,
            metadata={"original_role": message.role}
        )

        self.context_items.append(context_item)

    def add_system_context(self, content: str, priority: ContextPriority = ContextPriority.CRITICAL) -> None:
        """添加系统上下文"""
        context_item = ContextItem(
            content=content,
            priority=priority,
            category="system",
            metadata={"type": "system_prompt"}
        )
        self.context_items.insert(0, context_item)  # 系统内容放在最前面

    def add_tool_result(self, tool_name: str, result: Any, priority: ContextPriority = ContextPriority.HIGH) -> None:
        """添加工具执行结果"""
        # 简化长结果
        if isinstance(result, dict) and len(str(result)) > 1000:
            summary = self._summarize_dict_result(result)
            content = f"工具 {tool_name} 执行结果: {summary}"
        else:
            content = f"工具 {tool_name} 执行结果: {str(result)[:500]}{'...' if len(str(result)) > 500 else ''}"

        context_item = ContextItem(
            content=content,
            priority=priority,
            category="tool_result",
            metadata={"tool_name": tool_name, "original_result": result}
        )

        self.context_items.append(context_item)

    def optimize_context(self) -> List[ContextItem]:
        """
        优化上下文，返回适合当前窗口的上下文项列表

        Returns:
            优化后的上下文项列表
        """
        if not self.context_items:
            return []

        # 计算所有项目的token数
        for item in self.context_items:
            item.calculate_tokens(self.encoding_name)

        total_tokens = sum(item.token_count for item in self.context_items)

        # 如果总token数在预算内，直接返回
        if total_tokens <= self.window.available_tokens:
            return self.context_items.copy()

        # 需要压缩上下文
        return self._compress_context()

    def _compress_context(self) -> List[ContextItem]:
        """压缩上下文以适应token预算"""
        optimized_items = []

        # 1. 始终保留高优先级和系统内容
        critical_items = [item for item in self.context_items
                         if item.priority in (ContextPriority.CRITICAL, ContextPriority.HIGH)]
        optimized_items.extend(critical_items)

        # 2. 计算已使用的token数
        used_tokens = sum(item.token_count for item in optimized_items)
        remaining_tokens = self.window.available_tokens - used_tokens

        if remaining_tokens <= 0:
            # 空间不足，只保留最关键的内容
            return optimized_items[:1] if optimized_items else []

        # 3. 选择性保留中等优先级内容
        medium_items = [item for item in self.context_items
                       if item.priority == ContextPriority.MEDIUM]

        # 按时间倒序（最新的优先）
        medium_items.sort(key=lambda x: x.created_at, reverse=True)

        for item in medium_items:
            if used_tokens + item.token_count <= self.window.available_tokens:
                optimized_items.append(item)
                used_tokens += item.token_count
            else:
                # 尝试压缩这个项目
                compressed_item = self._compress_item(item, remaining_tokens)
                if compressed_item:
                    optimized_items.append(compressed_item)
                    used_tokens += compressed_item.token_count
                break

        return optimized_items

    def _compress_item(self, item: ContextItem, max_tokens: int) -> Optional[ContextItem]:
        """压缩单个上下文项"""
        if item.token_count <= max_tokens:
            return item

        # 对于长内容，进行摘要
        if item.category in ("assistant", "user"):
            # 对话内容可以截断
            compressed_content = self._truncate_content(item.content, max_tokens)
            if compressed_content:
                compressed_item = ContextItem(
                    content=f"[压缩] {compressed_content}",
                    priority=item.priority,
                    category=f"{item.category}_compressed",
                    metadata={**item.metadata, "compressed": True, "original_length": item.token_count}
                )
                compressed_item.calculate_tokens(self.encoding_name)
                return compressed_item

        elif item.category == "tool_result":
            # 工具结果可以简化
            compressed_content = f"[工具结果摘要] {item.metadata.get('tool_name', 'unknown')}: 执行完成"
            compressed_item = ContextItem(
                content=compressed_content,
                priority=max(item.priority, ContextPriority.LOW),  # 降低优先级
                category="tool_result_compressed",
                metadata={**item.metadata, "compressed": True}
            )
            compressed_item.calculate_tokens(self.encoding_name)
            return compressed_item

        return None  # 无法压缩

    def _truncate_content(self, content: str, max_tokens: int) -> str:
        """智能截断内容"""
        try:
            if tiktoken is None:
                raise RuntimeError("tiktoken_missing")
            encoding = tiktoken.get_encoding(self.encoding_name)
            tokens = encoding.encode(content)

            if len(tokens) <= max_tokens:
                return content

            # 保留前80%的内容，后20%截断
            keep_tokens = int(max_tokens * 0.8)
            truncated_tokens = tokens[:keep_tokens]
            truncated_content = encoding.decode(truncated_tokens)

            return f"{truncated_content}... [内容已截断，节省 {len(tokens) - keep_tokens} 个token]"

        except Exception:
            # 简单字符截断
            max_chars = max_tokens * 3  # 粗略估算
            if len(content) <= max_chars:
                return content
            return f"{content[:max_chars]}... [内容已截断]"

    def _summarize_tool_calls(self, tool_calls: List[Dict[str, Any]]) -> str:
        """总结工具调用信息"""
        if not tool_calls:
            return "无工具调用"

        tool_names = [call.get("function", {}).get("name", "unknown") for call in tool_calls]
        return f"工具: {', '.join(tool_names[:3])}{'...' if len(tool_names) > 3 else ''}"

    def _summarize_dict_result(self, result: Dict[str, Any]) -> str:
        """总结字典结果"""
        keys = list(result.keys())
        if len(keys) <= 3:
            return f"包含字段: {', '.join(keys)}"
        else:
            return f"包含 {len(keys)} 个字段: {', '.join(keys[:3])} 等"

    def get_context_stats(self) -> Dict[str, Any]:
        """获取上下文统计信息"""
        if not self.context_items:
            return {"total_items": 0, "total_tokens": 0, "categories": {}}

        total_tokens = sum(item.calculate_tokens(self.encoding_name) for item in self.context_items)

        categories = {}
        for item in self.context_items:
            categories[item.category] = categories.get(item.category, 0) + 1

        priorities = {}
        for item in self.context_items:
            priorities[item.priority.name] = priorities.get(item.priority.name, 0) + 1

        return {
            "total_items": len(self.context_items),
            "total_tokens": total_tokens,
            "available_tokens": self.window.available_tokens,
            "utilization_rate": total_tokens / self.window.max_tokens if self.window.max_tokens > 0 else 0,
            "categories": categories,
            "priorities": priorities
        }

    def clear_context(self, keep_system: bool = True) -> None:
        """清空上下文"""
        if keep_system:
            # 保留系统消息
            system_items = [item for item in self.context_items if item.category == "system"]
            self.context_items = system_items
        else:
            self.context_items.clear()

    def set_token_budget(self, max_tokens: int, reserved_tokens: int = 1000) -> None:
        """设置token预算"""
        self.window.max_tokens = max_tokens
        self.window.reserved_tokens = reserved_tokens


# 全局上下文管理器实例
_context_manager: Optional[AdvancedContextManager] = None

def get_advanced_context_manager(max_tokens: int = 4000) -> AdvancedContextManager:
    """获取高级上下文管理器实例"""
    global _context_manager
    if _context_manager is None:
        _context_manager = AdvancedContextManager(max_tokens=max_tokens)
    return _context_manager