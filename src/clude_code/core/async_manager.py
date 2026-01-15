"""
异步任务管理器，用于管理长时间运行的操作和进度跟踪
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Callable, Dict, Optional, Union
from dataclasses import dataclass, field
from enum import Enum

from clude_code.observability.logger import get_logger


class TaskStatus(Enum):
    """任务状态枚举"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TaskProgress:
    """任务进度信息"""
    task_id: str
    status: TaskStatus
    progress: float  # 0.0 - 1.0
    message: str
    start_time: float
    estimated_end_time: Optional[float] = None
    result: Optional[Any] = None
    error: Optional[Exception] = None
    details: Dict[str, Any] = field(default_factory=dict)


class AsyncTaskManager:
    """异步任务管理器，用于管理长时间运行的操作"""
    
    def __init__(self, workspace_root: str):
        self.workspace_root = workspace_root
        self.logger = get_logger(__name__, workspace_root=workspace_root)
        self.tasks: Dict[str, TaskProgress] = {}
        self.task_futures: Dict[str, asyncio.Task] = {}
        self.progress_callbacks: Dict[str, Callable[[TaskProgress], None]] = {}
    
    async def create_task(
        self,
        task_id: str,
        coro,
        progress_callback: Optional[Callable[[TaskProgress], None]] = None
    ) -> str:
        """创建异步任务"""
        if task_id in self.tasks:
            self.logger.warning(f"Task {task_id} already exists, replacing it")
            await self.cancel_task(task_id)
        
        task_progress = TaskProgress(
            task_id=task_id,
            status=TaskStatus.PENDING,
            progress=0.0,
            message="准备中...",
            start_time=time.time()
        )
        self.tasks[task_id] = task_progress
        if progress_callback:
            self.progress_callbacks[task_id] = progress_callback
        
        # 创建包装协程，用于更新进度
        async def wrapped_coro():
            try:
                task_progress.status = TaskStatus.RUNNING
                task_progress.message = "执行中..."
                self._notify_progress(task_progress)
                
                result = await coro
                task_progress.status = TaskStatus.COMPLETED
                task_progress.progress = 1.0
                task_progress.message = "已完成"
                task_progress.result = result
                self._notify_progress(task_progress)
                return result
            except asyncio.CancelledError:
                task_progress.status = TaskStatus.CANCELLED
                task_progress.message = "已取消"
                self._notify_progress(task_progress)
                raise
            except Exception as e:
                task_progress.status = TaskStatus.FAILED
                task_progress.message = f"失败: {str(e)}"
                task_progress.error = e
                self._notify_progress(task_progress)
                raise
        
        task = asyncio.create_task(wrapped_coro())
        self.task_futures[task_id] = task
        self.logger.debug(f"Created async task: {task_id}")
        return task_id
    
    def update_task_progress(
        self,
        task_id: str,
        progress: float,
        message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        estimated_end_time: Optional[float] = None
    ) -> None:
        """更新任务进度（从任务内部调用）"""
        if task_id not in self.tasks:
            return
        
        task = self.tasks[task_id]
        task.progress = progress
        if message:
            task.message = message
        if details:
            task.details.update(details)
        if estimated_end_time:
            task.estimated_end_time = estimated_end_time
        elif progress > 0.1 and task.estimated_end_time is None:
            # 基于当前进度估算结束时间
            elapsed = time.time() - task.start_time
            estimated_total = elapsed / progress
            task.estimated_end_time = task.start_time + estimated_total
        
        self._notify_progress(task)
    
    def _notify_progress(self, task_progress: TaskProgress) -> None:
        """通知进度更新"""
        callback = self.progress_callbacks.get(task_progress.task_id)
        if callback:
            try:
                callback(task_progress)
            except Exception as e:
                self.logger.error(f"Error in progress callback for task {task_progress.task_id}: {e}")
    
    def get_progress(self, task_id: str) -> Optional[TaskProgress]:
        """获取任务进度"""
        return self.tasks.get(task_id)
    
    def get_all_tasks(self) -> Dict[str, TaskProgress]:
        """获取所有任务进度"""
        return self.tasks.copy()
    
    async def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        if task_id not in self.task_futures:
            return False
        
        future = self.task_futures[task_id]
        future.cancel()
        
        try:
            await future
        except asyncio.CancelledError:
            pass
        
        if task_id in self.tasks:
            self.tasks[task_id].status = TaskStatus.CANCELLED
            self.tasks[task_id].message = "已取消"
            self._notify_progress(self.tasks[task_id])
        
        self.logger.debug(f"Cancelled task: {task_id}")
        return True
    
    async def wait_for_task(self, task_id: str) -> Any:
        """等待任务完成"""
        if task_id not in self.task_futures:
            raise ValueError(f"Task {task_id} not found")
        
        return await self.task_futures[task_id]
    
    async def wait_for_all_tasks(self) -> Dict[str, Any]:
        """等待所有任务完成"""
        if not self.task_futures:
            return {}
        
        task_ids = list(self.task_futures.keys())
        results = {}
        
        for task_id in task_ids:
            try:
                results[task_id] = await self.wait_for_task(task_id)
            except Exception as e:
                self.logger.error(f"Task {task_id} failed: {e}")
                results[task_id] = e
        
        return results
    
    def cleanup_completed_tasks(self) -> None:
        """清理已完成的任务"""
        completed_task_ids = [
            task_id for task_id, task in self.tasks.items()
            if task.status in {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}
        ]
        
        for task_id in completed_task_ids:
            if task_id in self.task_futures:
                del self.task_futures[task_id]
            if task_id in self.progress_callbacks:
                del self.progress_callbacks[task_id]
            # 保留任务历史，但可以添加一个清理策略
            # del self.tasks[task_id]
        
        if completed_task_ids:
            self.logger.debug(f"Cleaned up {len(completed_task_ids)} completed tasks")


# 全局异步任务管理器实例
_global_async_manager: Optional[AsyncTaskManager] = None


def get_async_manager(workspace_root: str) -> AsyncTaskManager:
    """获取全局异步任务管理器实例"""
    global _global_async_manager
    if _global_async_manager is None:
        _global_async_manager = AsyncTaskManager(workspace_root)
    return _global_async_manager


def reset_async_manager() -> None:
    """重置全局异步任务管理器实例（主要用于测试）"""
    global _global_async_manager
    _global_async_manager = None