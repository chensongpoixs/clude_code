"""
Task tool - 任务代理工具

启动和管理系统中的子代理，用于处理复杂多步骤任务。
"""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Callable
from enum import Enum

from clude_code.tooling.types import ToolResult, ToolError


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentType(Enum):
    GENERAL = "general"
    EXPLORE = "explore"
    CODE_REVIEW = "code_review"
    TEST = "test"
    DEBUG = "debug"


@dataclass
class SubAgentTask:
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    description: str = ""
    prompt: str = ""
    agent_type: AgentType = AgentType.GENERAL
    status: TaskStatus = TaskStatus.PENDING
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: Optional[str] = None
    result: Optional[Any] = None
    error: Optional[str] = None
    session_id: Optional[str] = None


class TaskManager:
    """任务管理器"""

    def __init__(self):
        self.tasks: Dict[str, SubAgentTask] = {}
        self.agent_handlers: Dict[AgentType, Callable] = {}

    def register_agent_handler(self, agent_type: AgentType, handler: Callable):
        """注册代理处理器"""
        self.agent_handlers[agent_type] = handler

    def create_task(
        self,
        description: str,
        prompt: str,
        agent_type: AgentType = AgentType.GENERAL,
        session_id: Optional[str] = None
    ) -> SubAgentTask:
        """创建新任务"""
        task = SubAgentTask(
            description=description,
            prompt=prompt,
            agent_type=agent_type,
            session_id=session_id
        )
        self.tasks[task.task_id] = task
        return task

    async def execute_task(self, task_id: str) -> Optional[Any]:
        """执行任务"""
        if task_id not in self.tasks:
            raise ValueError(f"Task {task_id} not found")

        task = self.tasks[task_id]
        task.status = TaskStatus.RUNNING

        try:
            handler = self.agent_handlers.get(task.agent_type)
            if not handler:
                raise ValueError(f"No handler registered for agent type {task.agent_type.value}")

            # 异步执行代理任务
            result = await handler(task.prompt, task.session_id)
            task.result = result
            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.now().isoformat()

            return result

        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
            task.completed_at = datetime.now().isoformat()
            raise

    def get_task_status(self, task_id: str) -> Optional[SubAgentTask]:
        """获取任务状态"""
        return self.tasks.get(task_id)

    def list_tasks(self, session_id: Optional[str] = None) -> List[SubAgentTask]:
        """列出任务"""
        tasks = list(self.tasks.values())
        if session_id:
            tasks = [t for t in tasks if t.session_id == session_id]
        return sorted(tasks, key=lambda x: x.created_at, reverse=True)

    def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        task = self.tasks.get(task_id)
        if task and task.status in [TaskStatus.PENDING, TaskStatus.RUNNING]:
            task.status = TaskStatus.CANCELLED
            task.completed_at = datetime.now().isoformat()
            return True
        return False


# 全局任务管理器实例
_task_manager: Optional[TaskManager] = None


def get_task_manager() -> TaskManager:
    """获取任务管理器实例"""
    global _task_manager
    if _task_manager is None:
        _task_manager = TaskManager()
        # 注册默认代理处理器（模拟）
        _task_manager.register_agent_handler(AgentType.GENERAL, general_agent_handler)
        _task_manager.register_agent_handler(AgentType.EXPLORE, explore_agent_handler)
    return _task_manager


async def general_agent_handler(prompt: str, session_id: Optional[str] = None) -> Any:
    """通用代理处理器"""
    # 模拟处理时间
    await asyncio.sleep(0.1)
    return {"type": "general", "result": f"Processed: {prompt[:100]}...", "session_id": session_id}


async def explore_agent_handler(prompt: str, session_id: Optional[str] = None) -> Any:
    """探索代理处理器"""
    await asyncio.sleep(0.1)
    return {"type": "explore", "result": f"Explored: {prompt[:100]}...", "session_id": session_id}


def run_task(
    description: str,
    prompt: str,
    subagent_type: str = "general",
    session_id: Optional[str] = None
) -> ToolResult:
    """
    运行子代理任务

    Args:
        description: 任务描述
        prompt: 代理提示
        subagent_type: 代理类型 (general/explore)
        session_id: 会话ID

    Returns:
        ToolResult: 任务执行结果
    """
    try:
        manager = get_task_manager()

        # 解析代理类型
        try:
            agent_type = AgentType(subagent_type.lower())
        except ValueError:
            return ToolResult(
                ok=False,
                error={
                    "message": f"Unknown agent type: {subagent_type}",
                    "code": "INVALID_AGENT_TYPE"
                }
            )

        # 创建任务
        task = manager.create_task(description, prompt, agent_type, session_id)

        # 在实际实现中，这里会异步启动任务
        # 现在同步执行模拟
        try:
            # 注意：这里是同步调用，实际应该异步
            result = asyncio.run(manager.execute_task(task.task_id))
        except Exception as e:
            return ToolResult(
                ok=False,
                error={
                    "message": f"Task execution failed: {str(e)}",
                    "code": "TASK_EXECUTION_FAILED"
                }
            )

        return ToolResult(
            ok=True,
            payload={
                "task_id": task.task_id,
                "description": task.description,
                "agent_type": task.agent_type.value,
                "status": task.status.value,
                "result": result,
                "session_id": session_id
            }
        )

    except Exception as e:
        return ToolResult(
            ok=False,
            error={
                "message": f"Failed to run task: {str(e)}",
                "code": "TASK_RUN_FAILED"
            }
        )


def get_task_status(task_id: str) -> ToolResult:
    """
    获取任务状态

    Args:
        task_id: 任务ID

    Returns:
        ToolResult: 任务状态信息
    """
    try:
        manager = get_task_manager()
        task = manager.get_task_status(task_id)

        if not task:
            return ToolResult(
                ok=False,
                error={
                    "message": f"Task {task_id} not found",
                    "code": "TASK_NOT_FOUND"
                }
            )

        return ToolResult(
            ok=True,
            payload={
                "task_id": task.task_id,
                "status": task.status.value,
                "description": task.description,
                "agent_type": task.agent_type.value,
                "created_at": task.created_at,
                "completed_at": task.completed_at,
                "result": task.result,
                "error": task.error,
                "session_id": task.session_id
            }
        )

    except Exception as e:
        return ToolResult(
            ok=False,
            error={
                "message": f"Failed to get task status: {str(e)}",
                "code": "TASK_STATUS_FAILED"
            }
        )