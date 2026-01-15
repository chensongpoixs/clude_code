"""
智能上下文预算管理工具
参考Claude Code，实现精确的token预算分配和上下文优化
"""
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import math


class BudgetCategory(Enum):
    """预算类别"""
    SYSTEM = "system"          # 系统提示词
    TOOLS = "tools"           # 工具描述
    HISTORY = "history"       # 对话历史
    CONTEXT = "context"       # 代码上下文
    SCRATCHPAD = "scratchpad" # 推理空间
    OUTPUT = "output"         # 输出空间


@dataclass
class TokenBudget:
    """Token预算分配"""
    total_tokens: int
    reserved_output: int = 1000  # 为模型输出预留的token数

    # 各部分预算比例（占可用token的比例）
    budget_ratios = {
        BudgetCategory.SYSTEM: 0.15,      # 15% 用于系统提示
        BudgetCategory.TOOLS: 0.20,       # 20% 用于工具描述
        BudgetCategory.CONTEXT: 0.25,     # 25% 用于代码上下文
        BudgetCategory.HISTORY: 0.30,     # 30% 用于对话历史
        BudgetCategory.SCRATCHPAD: 0.10,  # 10% 用于推理空间
    }

    @property
    def available_tokens(self) -> int:
        """实际可用的token数"""
        return max(0, self.total_tokens - self.reserved_output)

    def get_budget_for(self, category: BudgetCategory) -> int:
        """获取指定类别的token预算"""
        ratio = self.budget_ratios.get(category, 0.1)
        return int(self.available_tokens * ratio)

    def calculate_optimal_history_length(self, avg_message_tokens: int = 200) -> int:
        """计算最优的历史消息长度"""
        history_budget = self.get_budget_for(BudgetCategory.HISTORY)
        max_messages = max(1, history_budget // avg_message_tokens)

        # 确保至少保留最近的几条消息
        return max(3, min(max_messages, 20))

    def should_compress_context(self, current_usage: float) -> bool:
        """判断是否应该压缩上下文"""
        return current_usage > 0.85  # 使用率超过85%时压缩

    def get_compression_strategy(self, current_usage: float) -> str:
        """获取压缩策略"""
        if current_usage > 0.95:
            return "aggressive"  # 激进压缩
        elif current_usage > 0.90:
            return "moderate"    # 中等压缩
        elif current_usage > 0.85:
            return "light"       # 轻微压缩
        else:
            return "none"        # 不压缩


class ContextCompressor:
    """
    上下文压缩器
    智能压缩上下文内容以适应token预算
    """

    def __init__(self):
        self.compression_stats = {
            "original_tokens": 0,
            "compressed_tokens": 0,
            "compression_ratio": 1.0,
            "items_compressed": 0
        }

    def compress_message_history(self, messages: List[Dict[str, Any]],
                               max_tokens: int) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        压缩消息历史

        Args:
            messages: 原始消息列表
            max_tokens: 最大token数

        Returns:
            (压缩后的消息列表, 压缩统计信息)
        """
        if not messages:
            return [], self.compression_stats

        # 重置统计信息
        self._reset_stats()

        # 估算每条消息的token数
        messages_with_tokens = []
        for msg in messages:
            token_count = self._estimate_tokens(msg.get('content', ''))
            messages_with_tokens.append({
                **msg,
                'token_count': token_count,
                'priority': self._calculate_message_priority(msg)
            })

        total_tokens = sum(msg['token_count'] for msg in messages_with_tokens)

        if total_tokens <= max_tokens:
            return messages, self.compression_stats

        # 需要压缩
        compressed_messages = self._compress_messages(messages_with_tokens, max_tokens)

        # 更新统计信息
        final_tokens = sum(msg.get('token_count', 0) for msg in compressed_messages)
        self.compression_stats.update({
            "original_tokens": total_tokens,
            "compressed_tokens": final_tokens,
            "compression_ratio": final_tokens / total_tokens if total_tokens > 0 else 1.0,
            "items_compressed": len([msg for msg in compressed_messages if msg.get('compressed', False)])
        })

        return compressed_messages, self.compression_stats

    def _compress_messages(self, messages: List[Dict[str, Any]], max_tokens: int) -> List[Dict[str, Any]]:
        """压缩消息列表"""
        # 1. 始终保留最新的消息
        compressed = []
        current_tokens = 0

        # 从最新的消息开始添加
        for msg in reversed(messages):
            token_count = msg['token_count']

            if current_tokens + token_count <= max_tokens:
                compressed.insert(0, msg)
                current_tokens += token_count
            else:
                # 尝试压缩这条消息
                compressed_msg = self._compress_single_message(msg, max_tokens - current_tokens)
                if compressed_msg:
                    compressed.insert(0, compressed_msg)
                    current_tokens += compressed_msg.get('token_count', token_count // 2)
                # 如果无法压缩，跳过这条消息

        return compressed

    def _compress_single_message(self, message: Dict[str, Any], max_tokens: int) -> Optional[Dict[str, Any]]:
        """压缩单个消息"""
        content = message.get('content', '')
        original_tokens = message.get('token_count', 0)

        if original_tokens <= max_tokens:
            return message

        # 根据消息类型选择压缩策略
        msg_type = message.get('role', 'unknown')

        if msg_type == 'system':
            # 系统消息尽量不压缩
            return self._compress_system_message(message, max_tokens)
        elif msg_type in ('user', 'assistant'):
            # 对话消息可以截断
            return self._compress_dialogue_message(message, max_tokens)
        else:
            # 其他消息类型
            return self._compress_other_message(message, max_tokens)

    def _compress_system_message(self, message: Dict[str, Any], max_tokens: int) -> Optional[Dict[str, Any]]:
        """压缩系统消息"""
        content = message.get('content', '')

        # 系统消息保持关键部分
        essential_parts = []
        lines = content.split('\n')

        for line in lines:
            line = line.strip()
            if any(keyword in line.lower() for keyword in ['important', 'critical', 'must', '核心', '关键']):
                essential_parts.append(line)

        if essential_parts:
            compressed_content = '\n'.join(essential_parts[:3])  # 最多保留3个关键部分
            return {
                **message,
                'content': f'[压缩的系统提示] {compressed_content}',
                'compressed': True,
                'original_tokens': message.get('token_count', 0)
            }

        return None  # 如果没有找到关键部分，宁可不保留

    def _compress_dialogue_message(self, message: Dict[str, Any], max_tokens: int) -> Optional[Dict[str, Any]]:
        """压缩对话消息"""
        content = message.get('content', '')

        # 估算可以保留的字符数
        max_chars = max_tokens * 3  # 粗略估算

        if len(content) <= max_chars:
            return message

        # 截断内容，保留前80%
        keep_chars = int(max_chars * 0.8)
        compressed_content = content[:keep_chars]

        # 添加截断标记
        compressed_content += f"\n\n[内容已压缩，节省约 {len(content) - keep_chars} 个字符]"

        return {
            **message,
            'content': compressed_content,
            'compressed': True,
            'original_tokens': message.get('token_count', 0),
            'compression_saved': len(content) - len(compressed_content)
        }

    def _compress_other_message(self, message: Dict[str, Any], max_tokens: int) -> Optional[Dict[str, Any]]:
        """压缩其他类型消息"""
        content = str(message.get('content', ''))

        # 对于其他消息，创建一个简短的摘要
        msg_type = message.get('role', 'unknown')
        compressed_content = f"[{msg_type}消息已压缩，原始长度: {len(content)} 字符]"

        return {
            **message,
            'content': compressed_content,
            'compressed': True,
            'original_tokens': message.get('token_count', 0)
        }

    def _calculate_message_priority(self, message: Dict[str, Any]) -> int:
        """计算消息优先级"""
        role = message.get('role', 'unknown')

        # 优先级映射
        priority_map = {
            'system': 10,
            'user': 8,
            'assistant': 7,
            'tool': 5,
            'error': 6,
        }

        base_priority = priority_map.get(role, 3)

        # 内容长度影响优先级（短消息通常更重要）
        content = message.get('content', '')
        if len(content) < 100:
            base_priority += 2

        return base_priority

    def _estimate_tokens(self, content: str) -> int:
        """估算内容的token数"""
        if not content:
            return 0

        # 简单估算：英文约1 token/单词，中文约1.5 token/字符
        # 这里使用一个简化的估算方法
        char_count = len(content)
        word_count = len(content.split())

        # 假设平均每个单词4个字符，中文字符按1.5倍计算
        english_chars = word_count * 4
        chinese_chars = char_count - english_chars

        english_tokens = word_count
        chinese_tokens = chinese_chars * 1.5

        return int(english_tokens + chinese_tokens)

    def _reset_stats(self):
        """重置统计信息"""
        self.compression_stats = {
            "original_tokens": 0,
            "compressed_tokens": 0,
            "compression_ratio": 1.0,
            "items_compressed": 0
        }


class SlidingWindowManager:
    """
    滑动窗口管理器
    实现高效的上下文滑动窗口管理
    """

    def __init__(self, window_size: int = 10, overlap: int = 2):
        self.window_size = window_size
        self.overlap = overlap
        self.windows: List[List[Any]] = []

    def add_item(self, item: Any) -> None:
        """添加项目到滑动窗口"""
        if not self.windows or len(self.windows[-1]) >= self.window_size:
            # 创建新窗口
            if self.windows:
                # 从上一个窗口复制重叠部分
                overlap_items = self.windows[-1][-self.overlap:] if self.overlap > 0 else []
                self.windows.append(overlap_items)
            else:
                self.windows.append([])

        if len(self.windows[-1]) < self.window_size:
            self.windows[-1].append(item)

    def get_current_window(self) -> List[Any]:
        """获取当前窗口"""
        return self.windows[-1] if self.windows else []

    def get_recent_windows(self, count: int = 3) -> List[List[Any]]:
        """获取最近的几个窗口"""
        return self.windows[-count:] if self.windows else []

    def get_window_stats(self) -> Dict[str, Any]:
        """获取窗口统计信息"""
        return {
            "total_windows": len(self.windows),
            "current_window_size": len(self.get_current_window()),
            "total_items": sum(len(w) for w in self.windows),
            "window_sizes": [len(w) for w in self.windows]
        }

    def clear_old_windows(self, keep_recent: int = 5) -> int:
        """清理旧窗口"""
        if len(self.windows) <= keep_recent:
            return 0

        removed_count = len(self.windows) - keep_recent
        self.windows = self.windows[-keep_recent:]
        return removed_count


# 全局实例
_token_budget: Optional[TokenBudget] = None
_context_compressor: Optional[ContextCompressor] = None
_sliding_window: Optional[SlidingWindowManager] = None

def get_token_budget(total_tokens: int = 4000) -> TokenBudget:
    """获取token预算管理器"""
    global _token_budget
    if _token_budget is None or _token_budget.total_tokens != total_tokens:
        _token_budget = TokenBudget(total_tokens=total_tokens)
    return _token_budget

def get_context_compressor() -> ContextCompressor:
    """获取上下文压缩器"""
    global _context_compressor
    if _context_compressor is None:
        _context_compressor = ContextCompressor()
    return _context_compressor

def get_sliding_window_manager(window_size: int = 10) -> SlidingWindowManager:
    """获取滑动窗口管理器"""
    global _sliding_window
    if _sliding_window is None or _sliding_window.window_size != window_size:
        _sliding_window = SlidingWindowManager(window_size=window_size)
    return _sliding_window