"""
Todo tools - 任务管理工具

提供任务列表的创建、更新和读取功能，帮助AI组织复杂的工作流程。
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional
from enum import Enum

from clude_code.tooling.types import ToolResult, ToolError
from ..logger_helper import get_tool_logger
from ...config.tools_config import get_task_config

# 工具模块 logger（延迟初始化）
_logger = get_tool_logger(__name__)


class TodoStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


@dataclass
class TodoItem:
    content: str
    status: TodoStatus = TodoStatus.PENDING
    priority: str = "medium"  # high, medium, low
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())


class TodoManager:
    """任务管理器"""

    def __init__(self, storage_path: Optional[str] = None):
        self.storage_path = storage_path
        self.todos: Dict[str, TodoItem] = {}
        self._load_todos()

    def _load_todos(self):
        """从文件加载任务"""
        if not self.storage_path:
            return
        try:
            with open(self.storage_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for item_data in data.get('todos', []):
                    item = TodoItem(**item_data)
                    self.todos[item.id] = item
        except (FileNotFoundError, json.JSONDecodeError):
            pass

    def _save_todos(self):
        """保存任务到文件"""
        if not self.storage_path:
            return
        try:
            data = {
                'todos': [
                    {
                        'content': item.content,
                        'status': item.status.value,
                        'priority': item.priority,
                        'id': item.id,
                        'created_at': item.created_at,
                        'updated_at': item.updated_at
                    }
                    for item in self.todos.values()
                ]
            }
            with open(self.storage_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass  # 保存失败时静默处理

    def create_todo(self, content: str, priority: str = "medium") -> TodoItem:
        """创建新任务"""
        item = TodoItem(content=content, priority=priority)
        self.todos[item.id] = item
        self._save_todos()
        return item

    def update_todo(self, todo_id: str, **updates) -> Optional[TodoItem]:
        """更新任务"""
        if todo_id not in self.todos:
            return None

        item = self.todos[todo_id]
        for key, value in updates.items():
            if hasattr(item, key):
                setattr(item, key, value)

        item.updated_at = datetime.now().isoformat()
        self._save_todos()
        return item

    def get_todo(self, todo_id: str) -> Optional[TodoItem]:
        """获取单个任务"""
        return self.todos.get(todo_id)

    def list_todos(self, status: Optional[TodoStatus] = None) -> List[TodoItem]:
        """列出任务"""
        todos = list(self.todos.values())
        if status:
            todos = [t for t in todos if t.status == status]
        return sorted(todos, key=lambda x: x.created_at)

    def delete_todo(self, todo_id: str) -> bool:
        """删除任务"""
        if todo_id in self.todos:
            del self.todos[todo_id]
            self._save_todos()
            return True
        return False


# 全局任务管理器实例
_todo_manager: Optional[TodoManager] = None


def get_todo_manager() -> TodoManager:
    """获取任务管理器实例"""
    global _todo_manager
    if _todo_manager is None:
        # 可以在此处配置存储路径
        _todo_manager = TodoManager()
    return _todo_manager


def todowrite(
    content: str,
    priority: str = "medium",
    status: str = "pending"
) -> ToolResult:
    """
    创建或更新任务列表

    Args:
        content: 任务内容
        priority: 优先级 (high/medium/low)
        status: 状态 (pending/in_progress/completed/cancelled)

    Returns:
        ToolResult: 任务创建结果
    """
    # 检查工具是否启用
    config = get_task_config()
    if not config.enabled:
        _logger.warning("[Todo] 任务管理工具已被禁用")
        return ToolResult(False, error={"code": "E_TOOL_DISABLED", "message": "task tool is disabled"})

    try:
        manager = get_todo_manager()

        # 如果是更新现有任务
        if content.startswith("update:"):
            parts = content.split(":", 2)
            if len(parts) == 3:
                todo_id = parts[1].strip()
                new_content = parts[2].strip()
                item = manager.update_todo(todo_id, content=new_content, status=TodoStatus(status))
                if item:
                    return ToolResult(
                        ok=True,
                        payload={
                            "action": "updated",
                            "todo": {
                                "id": item.id,
                                "content": item.content,
                                "status": item.status.value,
                                "priority": item.priority
                            }
                        }
                    )

        # 创建新任务
        item = manager.create_todo(content, priority)
        item.status = TodoStatus(status)

        return ToolResult(
            ok=True,
            payload={
                "action": "created",
                "todo": {
                    "id": item.id,
                    "content": item.content,
                    "status": item.status.value,
                    "priority": item.priority,
                    "created_at": item.created_at
                }
            }
        )

    except Exception as e:
        return ToolResult(
            ok=False,
            error={
                "message": f"Failed to manage todo: {str(e)}",
                "code": "TODO_MANAGE_FAILED"
            }
        )


def todoread(
    status: Optional[str] = None,
    todo_id: Optional[str] = None
) -> ToolResult:
    """
    读取任务列表

    Args:
        status: 过滤状态 (pending/in_progress/completed/cancelled)
        todo_id: 特定任务ID

    Returns:
        ToolResult: 任务列表
    """
    try:
        # 检查工具是否启用
        config = get_task_config()
        if not config.enabled:
            _logger.warning("[Todo] 任务管理工具已被禁用")
            return ToolResult(False, error={"code": "E_TOOL_DISABLED", "message": "task tool is disabled"})

        _logger.debug(f"[Todo] 开始读取任务: status={status}, todo_id={todo_id}")
        manager = get_todo_manager()

        if todo_id:
            item = manager.get_todo(todo_id)
            if not item:
                _logger.warning(f"[Todo] 任务未找到: todo_id={todo_id}")
                return ToolResult(
                    ok=False,
                    error={
                        "message": f"Todo with ID {todo_id} not found",
                        "code": "TODO_NOT_FOUND"
                    }
                )
            todos = [item]
        else:
            status_filter = TodoStatus(status) if status else None
            todos = manager.list_todos(status_filter)

        todo_list = [
            {
                "id": item.id,
                "content": item.content,
                "status": item.status.value,
                "priority": item.priority,
                "created_at": item.created_at,
                "updated_at": item.updated_at
            }
            for item in todos
        ]

        _logger.info(f"[Todo] 任务读取成功: count={len(todo_list)}, filter={status}")
        return ToolResult(
            ok=True,
            payload={
                "todos": todo_list,
                "count": len(todo_list),
                "filter": status
            }
        )

    except Exception as e:
        _logger.error(f"[Todo] 任务读取失败: {e}", exc_info=True)
        return ToolResult(
            ok=False,
            error={
                "message": f"Failed to read todos: {str(e)}",
                "code": "TODO_READ_FAILED"
            }
        )