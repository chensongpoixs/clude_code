"""
AgentLoop（目录化模块入口）。

说明（大文件治理）：
- 旧路径：`clude_code.orchestrator.agent_loop` 曾经是单文件 `agent_loop.py`
- 现在改为包目录：`agent_loop/`
- 对外 API 保持不变：仍然支持 `from clude_code.orchestrator.agent_loop import AgentLoop`
"""

from .agent_loop import AgentLoop  # noqa: F401
from .models import AgentTurn  # noqa: F401


