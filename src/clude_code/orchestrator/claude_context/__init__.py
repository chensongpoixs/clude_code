"""
Claude Code 标准上下文管理器包

基于Claude Code官方最佳实践实现的上下文管理系统，解决：
1. 重复系统消息bug
2. Token超限处理
3. Auto-Compact机制
4. 优先级保护策略

核心特性：
- 70%阈值触发auto-compact
- 5层优先级保护体系
- 15%完成缓冲区
- 紧急模式处理
- 智能压缩算法

使用示例：
```python
from clude_code.orchestrator.claude_context import get_claude_context_manager

# 创建Claude Code标准管理器
manager = get_claude_context_manager(max_tokens=200000)

# 添加系统消息（自动保护）
manager.add_system_context("你是一个AI助手")

# 添加对话（自动触发auto-compact）
manager.add_message("用户输入", priority=ContextPriority.RECENT)

# 检查状态
stats = manager.get_context_stats()
```
"""

from .core import (
    ContextPriority,
    ClaudeContextItem,
    ClaudeContextWindow,
    ClaudeCodeContextManager
)
from .manager import get_claude_context_manager

__all__ = [
    'ContextPriority',
    'ClaudeContextItem', 
    'ClaudeContextWindow',
    'ClaudeCodeContextManager',
    'get_claude_context_manager'
]

__version__ = "1.0.0"
__author__ = "Claude Code开发团队"
__description__ = "Claude Code标准上下文管理器"