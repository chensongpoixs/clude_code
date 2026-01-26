"""
上下文管理模块

基于Claude Code官方最佳实践，提供多层次上下文管理解决方案：

模块结构：
- claude_standard/: Claude Code标准实现
- industry_standard/: 业界通用标准实现  
- utils/: 通用工具和辅助函数

核心功能：
- 重复系统消息修复
- Token超限处理
- Auto-Compact机制
- 智能压缩算法
- 优先级保护策略

使用示例：
```python
# Claude Code标准
from clude_code.context.claude_standard import get_claude_context_manager

# 业界标准
from clude_code.context.industry_standard import get_industry_context_manager
```

选择建议：
- Claude Code项目：使用claude_standard
- 通用AI项目：使用industry_standard
- 定制化需求：继承基类扩展
"""

# 核心接口统一
from .claude_standard import (
    ClaudeContextManager,
    get_claude_context_manager,
    ContextPriority
)

# 备选方案 - 待实现
# from .industry_standard import (
#     IndustryContextManager, 
#     get_industry_context_manager
# )

# 通用工具 - 待实现
# from .utils import (
#     TokenCalculator,
#     ContentNormalizer,
#     CompressionHelper
# )

__all__ = [
    # Claude Code标准（推荐）
    'ClaudeContextManager',
    'get_claude_context_manager', 
    'ContextPriority',
    
    # 业界标准（待实现）
    # 'IndustryContextManager',
    # 'get_industry_context_manager',
    
    # 工具类（待实现）
    # 'TokenCalculator',
    # 'ContentNormalizer', 
    # 'CompressionHelper'
]

__version__ = "2.0.0"
__description__ = "多标准上下文管理模块"
__author__ = "Claude Code开发团队"