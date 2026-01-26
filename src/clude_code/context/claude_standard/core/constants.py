"""
Claude Code标准核心数据结构

定义基础枚举、数据类和常量
"""
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any
import time


class ContextPriority(Enum):
    """Claude Code标准5层优先级体系
    
    设计理念：
    - PROTECTED: 系统提示词，绝对保护
    - RECENT: 最近5轮对话，高价值保留
    - WORKING: 当前工作记忆，中等优先级
    - RELEVANT: 相关历史，可压缩处理
    - ARCHIVAL: 存档信息，优先丢弃
    
    优先级指导原则：
    1. 系统消息永不丢弃
    2. 最近对话优先保护
    3. 历史信息可压缩
    4. 存档信息可丢弃
    """
    PROTECTED = 5      # 系统提示词 (绝对保护)
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
    def level_name(self) -> str:
        """优先级等级名称"""
        names = {
            ContextPriority.PROTECTED: "保护级",
            ContextPriority.RECENT: "最近级", 
            ContextPriority.WORKING: "工作级",
            ContextPriority.RELEVANT: "相关级",
            ContextPriority.ARCHIVAL: "存档级"
        }
        return names.get(self, "未知级")
    
    @property
    def description(self) -> str:
        """优先级详细描述"""
        descriptions = {
            ContextPriority.PROTECTED: "系统提示词，永不丢弃",
            ContextPriority.RECENT: "最近5轮对话，高价值保留",
            ContextPriority.WORKING: "当前工作记忆，中等优先级",
            ContextPriority.RELEVANT: "相关历史，可压缩处理", 
            ContextPriority.ARCHIVAL: "存档信息，优先丢弃"
        }
        return descriptions.get(self, "未知优先级")
    
    def is_protected_level(self) -> bool:
        """是否为保护级别"""
        return self in [ContextPriority.PROTECTED, ContextPriority.RECENT]
    
    def is_compressible(self) -> bool:
        """是否可压缩"""
        return self in [ContextPriority.RELEVANT, ContextPriority.ARCHIVAL]


class ContentType(Enum):
    """内容类型枚举"""
    SYSTEM = "system"           # 系统消息
    USER = "user"              # 用户输入
    ASSISTANT = "assistant"     # 助手回复
    TOOL_CALL = "tool_call"     # 工具调用
    TOOL_RESULT = "tool_result"  # 工具结果
    SUMMARY = "summary"         # 摘要内容
    COMPRESSED = "compressed"    # 压缩内容
    
    @property
    def is_dialogue(self) -> bool:
        """是否为对话内容"""
        return self in [ContentType.USER, ContentType.ASSISTANT]
    
    @property
    def is_tool_related(self) -> bool:
        """是否为工具相关"""
        return self in [ContentType.TOOL_CALL, ContentType.TOOL_RESULT]
    
    @property
    def is_system_type(self) -> bool:
        """是否为系统类型"""
        return self in [ContentType.SYSTEM, ContentType.SUMMARY]


@dataclass
class ContextMetadata:
    """上下文元数据"""
    original_role: str = ""
    compression_algorithm: str = ""
    original_length: int = 0
    compression_ratio: float = 0.0
    tool_name: str = ""
    protection_reason: str = ""
    created_session: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "original_role": self.original_role,
            "compression_algorithm": self.compression_algorithm,
            "original_length": self.original_length,
            "compression_ratio": self.compression_ratio,
            "tool_name": self.tool_name,
            "protection_reason": self.protection_reason,
            "created_session": self.created_session
        }


@dataclass
class ProtectionInfo:
    """保护信息"""
    is_protected: bool = False
    protection_reason: str = ""
    protection_level: int = 0
    expires_at: float = 0
    
    def set_protection(self, reason: str, level: int, expires: float = 0) -> None:
        """设置保护"""
        self.is_protected = True
        self.protection_reason = reason
        self.protection_level = level
        self.expires_at = expires
    
    def is_expired(self) -> bool:
        """是否已过期"""
        return self.expires_at > 0 and time.time() > self.expires_at


@dataclass
class CompressionResult:
    """压缩结果"""
    success: bool = False
    original_tokens: int = 0
    compressed_tokens: int = 0
    compression_ratio: float = 0.0
    algorithm_used: str = ""
    quality_score: float = 0.0  # 压缩质量评分
    
    @property
    def tokens_saved(self) -> int:
        """节省的token数"""
        return max(0, self.original_tokens - self.compressed_tokens)
    
    @property
    def efficiency_score(self) -> float:
        """效率评分"""
        if self.original_tokens == 0:
            return 0.0
        return self.tokens_saved / self.original_tokens
    
    def to_summary(self) -> Dict[str, Any]:
        """转换为摘要"""
        return {
            "success": self.success,
            "original_tokens": self.original_tokens,
            "compressed_tokens": self.compressed_tokens, 
            "tokens_saved": self.tokens_saved,
            "compression_ratio": self.compression_ratio,
            "algorithm_used": self.algorithm_used,
            "efficiency_score": self.efficiency_score,
            "quality_score": self.quality_score
        }


# 常量定义
class ClaudeCodeConstants:
    """Claude Code标准常量"""
    
    # 窗口配置
    DEFAULT_MAX_TOKENS = 200000      # Claude Code Pro标准
    COMPACT_THRESHOLD = 0.7           # 70%触发auto-compact
    COMPLETION_BUFFER = 0.15          # 15%完成缓冲区
    EMERGENCY_THRESHOLD = 0.9         # 90%紧急处理
    
    # 保护配置
    PROTECTED_ROUNDS = 5              # 保护最近5轮对话
    MAX_PROTECTED_ITEMS = 20           # 最多保护20个项目
    
    # 压缩配置
    MAX_COMPRESSION_ATTEMPTS = 3      # 最大压缩轮数
    MIN_COMPRESSION_RATIO = 0.3       # 最小压缩比例
    MAX_COMPRESSION_RATIO = 0.8       # 最大压缩比例
    
    # 质量阈值
    MIN_COMPRESSION_QUALITY = 0.6     # 最小压缩质量
    PREFERRED_COMPRESSION_QUALITY = 0.8  # 期望压缩质量
    
    # 性能限制
    MAX_COMPRESSION_TIME = 0.1        # 最大压缩时间(秒)
    MAX_CONTEXT_ITEMS = 1000          # 最大上下文项目数
    TOKEN_ESTIMATION_FACTOR = 0.7     # Token估算因子