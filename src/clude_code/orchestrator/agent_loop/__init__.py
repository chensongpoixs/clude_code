"""
AgentLoop（目录化模块入口）。

说明（大文件治理）：
- 旧路径：`clude_code.orchestrator.agent_loop` 曾经是单文件 `agent_loop.py`
- 现在改为包目录：`agent_loop/`
- 对外 API 保持不变：仍然支持 `from clude_code.orchestrator.agent_loop import AgentLoop`
"""

from __future__ import annotations

from typing import TYPE_CHECKING

# 重要：避免在包导入时做“重型导入”。
# 否则 `clude tools/doctor` 这类只读命令也会因为可选依赖（如 requests/fastembed/lancedb）
# 未安装而崩溃。业界做法是让 CLI 的信息类命令可以在最小依赖集下运行。

if TYPE_CHECKING:  # pragma: no cover
    from .agent_loop import AgentLoop as AgentLoop  # noqa: F401
    from .models import AgentTurn as AgentTurn  # noqa: F401


def __getattr__(name: str):
    if name == "AgentLoop":
        from .agent_loop import AgentLoop as _AgentLoop

        return _AgentLoop
    if name == "AgentTurn":
        from .models import AgentTurn as _AgentTurn

        return _AgentTurn
    raise AttributeError(name)


__all__ = ["AgentLoop", "AgentTurn"]


