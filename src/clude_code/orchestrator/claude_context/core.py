"""
Claude Code 标准上下文管理器核心类定义

包含基础数据结构和枚举类型
"""
import tiktoken
from typing import List, Dict, Any, Optional, Tuple, Union
from dataclasses import dataclass, field
from enum import Enum
import time

from clude_code.llm.http_client import ChatMessage


class ContextPriority(Enum):
    """Claude Code 标准优先级体系
    
    基于Claude Code官方实践的5层优先级：
    - PROTECTED: 系统提示词，永不丢弃
    - RECENT: 最近5轮对话，高优先级
    - WORKING: 当前工作记忆，中等优先级
    - RELEVANT: 相关历史，可压缩
    - ARCHIVAL: 存档信息，优先丢弃
    """
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
    
    @property
    def description(self) -> str:
        """优先级描述"""
        descriptions = {
            ContextPriority.PROTECTED: "保护级(系统消息)",
            ContextPriority.RECENT: "最近级(5轮对话)",
            ContextPriority.WORKING: "工作级(当前记忆)",
            ContextPriority.RELEVANT: "相关级(历史信息)",
            ContextPriority.ARCHIVAL: "存档级(旧信息)"
        }
        return descriptions.get(self, "未知级别")


@dataclass
class ClaudeContextItem:
    """Claude Code 标准上下文项
    
    扩展标准上下文项，增加Claude Code特有属性
    """
    content: str
    priority: ContextPriority
    category: str
    token_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    protected: bool = False  # Claude Code 的保护机制
    compressed: bool = False  # 是否已压缩
    
    def calculate_tokens(self, encoding_name: str = "cl100k_base") -> int:
        """计算token数量 (Claude标准)"""
        if self.token_count > 0:
            return self.token_count

        try:
            encoding = tiktoken.get_encoding(encoding_name)
            self.token_count = len(encoding.encode(self.content))
        except Exception:
            # Claude Code 标准估算：中英文混合
            # 1个中文字符≈1.5个token，1个英文单词≈1个token
            chinese_chars = len([c for c in self.content if '\u4e00' <= c <= '\u9fff'])
            english_chars = len(self.content) - chinese_chars
            self.token_count = int(chinese_chars * 1.5 + english_chars * 0.5)

        return self.token_count
    
    @property
    def size_info(self) -> str:
        """获取大小信息"""
        chars = len(self.content)
        tokens = self.calculate_tokens()
        return f"{chars}字符/{tokens}tokens"
    
    def is_high_priority(self) -> bool:
        """是否为高优先级"""
        return self.priority in [ContextPriority.PROTECTED, ContextPriority.RECENT]
    
    def can_compress(self) -> bool:
        """是否可以压缩"""
        return not self.protected and self.priority != ContextPriority.PROTECTED


@dataclass
class ClaudeContextWindow:
    """Claude Code 标准上下文窗口配置
    
    基于Claude Code官方实践的窗口管理参数
    """
    max_tokens: int
    compact_threshold: float = 0.7      # 70%时触发auto-compact
    completion_buffer: float = 0.15     # 15%完成缓冲区
    emergency_threshold: float = 0.9     # 90%时紧急处理
    
    @property
    def auto_compact_threshold(self) -> int:
        """自动压缩阈值token数"""
        return int(self.max_tokens * self.compact_threshold)
    
    @property
    def completion_buffer_tokens(self) -> int:
        """完成缓冲区token数"""
        return int(self.max_tokens * self.completion_buffer)
    
    @property
    def usable_tokens(self) -> int:
        """可用token数（扣除完成缓冲区）"""
        return int(self.max_tokens * (1 - self.completion_buffer))
    
    @property
    def emergency_threshold_tokens(self) -> int:
        """紧急处理阈值token数"""
        return int(self.max_tokens * self.emergency_threshold)
    
    @property
    def free_tokens(self) -> int:
        """剩余可用token数"""
        return self.usable_tokens - self.current_used  # 需要外部设置
    
    def get_status_info(self) -> str:
        """获取窗口状态信息"""
        return (f"窗口配置: {self.max_tokens:,}总tokens, "
                f"{self.compact_threshold:.0%}压缩阈值, "
                f"{self.completion_buffer:.0%}缓冲区, "
                f"{self.emergency_threshold:.0%}紧急阈值")


class CompressionStats:
    """压缩统计信息"""
    
    def __init__(self):
        self.total_compressions = 0
        self.tokens_saved = 0
        self.items_compressed = 0
        self.emergency_compressions = 0
        self.last_compaction_time = 0
        
    def record_compression(self, tokens_before: int, tokens_after: int, 
                         items_count: int, is_emergency: bool = False):
        """记录压缩统计"""
        self.total_compressions += 1
        self.tokens_saved += max(0, tokens_before - tokens_after)
        self.items_compressed += items_count
        if is_emergency:
            self.emergency_compressions += 1
        self.last_compaction_time = time.time()
    
    def get_efficiency_rate(self) -> float:
        """获取压缩效率"""
        if self.tokens_saved == 0:
            return 0.0
        return self.tokens_saved / max(1, self.items_compressed)
    
    def get_summary(self) -> Dict[str, Any]:
        """获取统计摘要"""
        return {
            "total_compressions": self.total_compressions,
            "tokens_saved": self.tokens_saved,
            "items_compressed": self.items_compressed,
            "emergency_compressions": self.emergency_compressions,
            "efficiency_rate": self.get_efficiency_rate(),
            "last_compaction": self.last_compaction_time
        }