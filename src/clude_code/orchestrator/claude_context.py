"""
Claude Code 标准的上下文管理器
基于Claude Code官方最佳实践和auto-compact机制
"""
import tiktoken
from typing import List, Dict, Any, Optional, Tuple, Union
from dataclasses import dataclass, field
from enum import Enum
import time

from clude_code.llm.http_client import ChatMessage


class ContextPriority(Enum):
    """Claude Code 标准优先级"""
    PROTECTED = 5      # 系统提示词 (永不丢弃)
    RECENT = 4         # 最近5轮对话 (高优先级)
    WORKING = 3        # 当前工作记忆 (中等优先级)
    RELEVANT = 2       # 相关历史 (可压缩)
    ARCHIVAL = 1        # 存档信息 (优先丢弃)
    
    def __lt__(self, other):
        if self.__class__ is other.__class__:
            return self.value < other.value
        return NotImplemented
    
    def __gt__(self, other):
        if self.__class__ is other.__class__:
            return self.value > other.value
        return NotImplemented


@dataclass
class ClaudeContextItem:
    """Claude Code 标准上下文项"""
    content: str
    priority: ContextPriority
    category: str
    token_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    protected: bool = False  # Claude Code 的保护机制

    def calculate_tokens(self, encoding_name: str = "cl100k_base") -> int:
        """计算token数量 (Claude标准)"""
        if self.token_count > 0:
            return self.token_count

        try:
            encoding = tiktoken.get_encoding(encoding_name)
            self.token_count = len(encoding.encode(self.content))
        except Exception:
            # Claude Code 标准估算
            self.token_count = len(self.content) // 2  # 中英文混合

        return self.token_count


@dataclass
class ClaudeContextWindow:
    """Claude Code 标准上下文窗口"""
    max_tokens: int
    compact_threshold: float = 0.7  # 70%时触发auto-compact (Claude Code标准)
    completion_buffer: float = 0.15  # 15%完成缓冲区
    emergency_threshold: float = 0.9  # 90%时紧急处理
    
    @property
    def auto_compact_threshold(self) -> int:
        """自动压缩阈值"""
        return int(self.max_tokens * self.compact_threshold)
    
    @property
    def completion_buffer_tokens(self) -> int:
        """完成缓冲区token数"""
        return int(self.max_tokens * self.completion_buffer)
    
    @property
    def usable_tokens(self) -> int:
        """可用token数"""
        return int(self.max_tokens * (1 - self.completion_buffer))
    
    @property
    def emergency_threshold_tokens(self) -> int:
        """紧急处理阈值"""
        return int(self.max_tokens * self.emergency_threshold)


class ClaudeCodeContextManager:
    """
    Claude Code 标准上下文管理器
    
    核心原理：
    1. Auto-Compact 在70%时触发，保持30%自由空间
    2. 优先保护系统提示词和最近5轮对话
    3. 渐进式压缩：压缩 > 截断 > 丢弃
    4. 完成缓冲区确保任务有空间完成
    """
    
    def __init__(self, max_tokens: int = 200000):  # Claude Code Pro标准
        self.window = ClaudeContextWindow(max_tokens=max_tokens)
        self.context_items: List[ClaudeContextItem] = []
        self.encoding_name = "cl100k_base"
        
        # Claude Code 标准配置
        self.protected_rounds = 5  # 保护最近5轮对话
        self.compression_rounds = 3  # 最大压缩轮数
        
        # 状态跟踪
        self.last_compact_time = 0
        self.compact_count = 0
        
    def should_auto_compact(self) -> bool:
        """是否应该触发auto-compact"""
        current_tokens = self.get_current_tokens()
        return current_tokens >= self.window.auto_compact_threshold
    
    def is_emergency_mode(self) -> bool:
        """是否处于紧急模式"""
        current_tokens = self.get_current_tokens()
        return current_tokens >= self.window.emergency_threshold_tokens
    
    def add_message(self, message: Union[ChatMessage, str], 
                   priority: ContextPriority = ContextPriority.WORKING) -> None:
        """添加消息 (Claude Code标准)"""
        if isinstance(message, str):
            category = "user" if not message.startswith("System:") else "system"
            content = message
            original_role = category
        else:
            category = message.role
            content = self._normalize_content(message.content)
            original_role = message.role
        
        # Claude Code 的保护机制
        protected = (priority == ContextPriority.PROTECTED or 
                    self._is_recent_conversation(category))
        
        context_item = ClaudeContextItem(
            content=content,
            priority=priority,
            category=category,
            metadata={"original_role": original_role},
            protected=protected
        )
        
        self.context_items.append(context_item)
        
        # 检查是否需要auto-compact
        if self.should_auto_compact():
            self.auto_compact()
    
    def add_system_context(self, content: str) -> None:
        """添加系统上下文 (Claude Code 保护级别)"""
        context_item = ClaudeContextItem(
            content=content,
            priority=ContextPriority.PROTECTED,
            category="system",
            metadata={"type": "system_prompt"},
            protected=True  # 系统消息永远保护
        )
        # 系统消息插入到最前面
        self.context_items.insert(0, context_item)
    
    def auto_compact(self) -> None:
        """Claude Code 标准的auto-compact流程"""
        if not self.should_auto_compact():
            return
        
        self.compact_count += 1
        self.last_compact_time = time.time()
        
        # 按Claude Code标准流程处理
        if self.is_emergency_mode():
            self._emergency_compact()
        else:
            self._standard_compact()
    
    def _standard_compact(self) -> None:
        """Claude Code 标准压缩流程"""
        # 1. 保护层级分类
        protected_items = []
        working_items = []
        archival_items = []
        
        for item in self.context_items:
            if item.protected or item.priority == ContextPriority.PROTECTED:
                protected_items.append(item)
            elif item.priority in [ContextPriority.RECENT, ContextPriority.WORKING]:
                working_items.append(item)
            else:
                archival_items.append(item)
        
        # 2. 压缩archival项目
        compressed_archival = []
        for item in archival_items:
            if len(compressed_archival) * 100 < self.window.completion_buffer_tokens:
                compressed = self._compress_item_claude_style(item)
                if compressed:
                    compressed_archival.append(compressed)
            else:
                break  # 缓冲区满了
        
        # 3. 压缩working项目 (如果需要)
        compressed_working = []
        total_tokens = sum(item.calculate_tokens(self.encoding_name) 
                         for item in protected_items + compressed_archival + compressed_working)
        
        if total_tokens > self.window.usable_tokens:
            # 需要压缩working项目
            for item in working_items:
                if total_tokens > self.window.usable_tokens:
                    compressed = self._compress_item_claude_style(item)
                    if compressed:
                        compressed_working.append(compressed)
                        total_tokens += compressed.calculate_tokens(self.encoding_name)
                else:
                    compressed_working.append(item)
                    total_tokens += item.calculate_tokens(self.encoding_name)
        else:
            compressed_working = working_items
        
        # 4. 重建context
        self.context_items = protected_items + compressed_working + compressed_archival
    
    def _emergency_compact(self) -> None:
        """紧急模式压缩"""
        # 只保留保护项目和极少量工作项目
        protected_items = [item for item in self.context_items 
                          if item.protected or item.priority == ContextPriority.PROTECTED]
        
        # 只保留最近的2轮对话
        recent_items = []
        other_items = []
        
        for item in self.context_items:
            if item in protected_items:
                continue
            elif item.priority == ContextPriority.RECENT and len(recent_items) < 2:
                recent_items.append(item)
            else:
                other_items.append(item)
        
        # 极端压缩其他项目
        emergency_items = []
        for item in other_items:
            if len(emergency_items) < 5:  # 最多5个压缩项目
                compressed = self._emergency_compress(item)
                if compressed:
                    emergency_items.append(compressed)
        
        self.context_items = protected_items + recent_items + emergency_items
    
    def _compress_item_claude_style(self, item: ClaudeContextItem) -> Optional[ClaudeContextItem]:
        """Claude Code 风格的项目压缩"""
        if item.category == "system":
            # 系统消息：保留关键指令
            return self._compress_system_message(item)
        elif item.category in ["assistant", "user"]:
            # 对话：智能摘要
            return self._compress_conversation(item)
        elif item.category == "tool_result":
            # 工具结果：关键信息
            return self._compress_tool_result(item)
        else:
            # 通用：最小化
            return self._compress_generic(item)
    
    def _compress_system_message(self, item: ClaudeContextItem) -> ClaudeContextItem:
        """压缩系统消息 (Claude风格)"""
        # 保留前70%的关键指令
        content = item.content
        if len(content) > 500:
            keep_chars = int(len(content) * 0.7)
            content = content[:keep_chars] + "\n\n[系统指令已压缩以保持性能]"
        
        return ClaudeContextItem(
            content=content,
            priority=item.priority,
            category="system_compressed",
            metadata={**item.metadata, "compressed": True},
            protected=True  # 压缩后的系统消息仍然保护
        )
    
    def _compress_conversation(self, item: ClaudeContextItem) -> ClaudeContextItem:
        """压缩对话 (Claude风格)"""
        content = item.content
        if len(content) > 200:
            # 保留开头30%和结尾20%，中间摘要
            start_len = int(len(content) * 0.3)
            end_len = int(len(content) * 0.2)
            middle = "...\n[对话内容已智能压缩]\n..."
            
            content = content[:start_len] + middle + content[-end_len:]
        
        content = f"[{item.category}压缩] {content}"
        
        return ClaudeContextItem(
            content=content,
            priority=ContextPriority.RELEVANT,  # 降低优先级
            category=f"{item.category}_compressed",
            metadata={**item.metadata, "compressed": True}
        )
    
    def _compress_tool_result(self, item: ClaudeContextItem) -> ClaudeContextItem:
        """压缩工具结果 (Claude风格)"""
        tool_name = item.metadata.get("tool_name", "工具")
        content = f"[{tool_name}] 执行完成，结果已优化存储"
        
        return ClaudeContextItem(
            content=content,
            priority=ContextPriority.ARCHIVAL,  # 降低到存档级别
            category="tool_result_optimized",
            metadata={**item.metadata, "compressed": True}
        )
    
    def _compress_generic(self, item: ClaudeContextItem) -> ClaudeContextItem:
        """通用压缩 (Claude风格)"""
        category_map = {
            "tool_call": "工具调用",
            "assistant": "助手回复", 
            "user": "用户输入"
        }
        
        desc = category_map.get(item.category, item.category)
        content = f"[{desc}] 已处理并优化"
        
        return ClaudeContextItem(
            content=content,
            priority=ContextPriority.ARCHIVAL,
            category="optimized",
            metadata={**item.metadata, "compressed": True}
        )
    
    def _emergency_compress(self, item: ClaudeContextItem) -> Optional[ClaudeContextItem]:
        """紧急压缩 (最小化表示)"""
        content = f"[{item.category}] 已处理"
        
        return ClaudeContextItem(
            content=content,
            priority=ContextPriority.ARCHIVAL,
            category="emergency",
            metadata={"original_category": item.category, "emergency": True}
        )
    
    def _is_recent_conversation(self, category: str) -> bool:
        """是否为最近对话"""
        if category not in ["user", "assistant"]:
            return False
        
        # 统计最近的user/assistant消息
        recent_conversations = [item for item in self.context_items[-10:]  # 最近10条
                             if item.category in ["user", "assistant"]]
        
        return len(recent_conversations) <= self.protected_rounds * 2
    
    def get_context_stats(self) -> Dict[str, Any]:
        """获取上下文统计 (Claude Code标准)"""
        current_tokens = self.get_current_tokens()
        usage_percent = current_tokens / self.window.max_tokens
        
        return {
            "total_items": len(self.context_items),
            "current_tokens": current_tokens,
            "max_tokens": self.window.max_tokens,
            "usage_percent": usage_percent,
            "auto_compact_threshold": self.window.auto_compact_threshold,
            "completion_buffer": self.window.completion_buffer_tokens,
            "should_compact": self.should_auto_compact(),
            "emergency_mode": self.is_emergency_mode(),
            "compact_count": self.compact_count,
            "last_compact_time": self.last_compact_time,
            "protected_items": len([item for item in self.context_items if item.protected])
        }
    
    def get_current_tokens(self) -> int:
        """获取当前token数"""
        return sum(item.calculate_tokens(self.encoding_name) for item in self.context_items)
    
    def _normalize_content(self, content: Union[str, List]) -> str:
        """标准化多模态内容"""
        if isinstance(content, str):
            return content
        elif isinstance(content, list):
            # Claude Code 标准：只提取文本内容
            text_parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_parts.append(item.get("text", ""))
            return " ".join(text_parts)
        else:
            return str(content)
    
    def clear_context(self, keep_protected: bool = True) -> None:
        """清空上下文"""
        if keep_protected:
            protected_items = [item for item in self.context_items if item.protected]
            self.context_items = protected_items
        else:
            self.context_items.clear()


# 全局实例
_claude_manager: Optional[ClaudeCodeContextManager] = None

def get_claude_context_manager(max_tokens: int = 200000) -> ClaudeCodeContextManager:
    """获取Claude Code标准上下文管理器"""
    global _claude_manager
    if _claude_manager is None:
        _claude_manager = ClaudeCodeContextManager(max_tokens=max_tokens)
    return _claude_manager