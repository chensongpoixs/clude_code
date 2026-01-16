"""
增强的实时显示组件，支持细粒度进度指示
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from collections import deque

from rich.console import Console, Group
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeRemainingColumn, TaskID
from rich.table import Table
from rich.text import Text
from rich.panel import Panel
from rich.live import Live
from rich.layout import Layout
from rich.align import Align

from clude_code.core.async_manager import TaskProgress, TaskStatus


class TaskType(Enum):
    """任务类型枚举"""
    LLM_REQUEST = "llm_request"
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    SEARCH = "search"
    COMMAND_EXEC = "command_exec"
    INDEXING = "indexing"
    VERIFICATION = "verification"
    PATCHING = "patching"


@dataclass
class TaskInfo:
    """任务信息"""
    task_id: str
    task_type: TaskType
    description: str
    progress: float = 0.0
    status: str = "running"
    start_time: float = field(default_factory=time.time)
    estimated_end_time: Optional[float] = None
    details: Dict[str, Any] = field(default_factory=dict)
    rich_task_id: Optional[TaskID] = None


class EnhancedLiveDisplay:
    """增强的实时显示组件，支持细粒度进度指示"""
    
    def __init__(self, console: Console, cfg: Any):
        self.console = console
        self.cfg = cfg
        self.start_time = time.time()
        
        # 任务管理
        self.active_tasks: Dict[str, TaskInfo] = {}
        self.completed_tasks: deque = deque(maxlen=5)
        self.task_counter = 0
        
        # 进度条组件
        self.progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeRemainingColumn(elapsed_when_finished=True),
            console=console,
            transient=True,
        )
        
        # 状态信息
        self.current_state = "初始化"
        self.current_operation = "等待中"
        self.last_events: deque = deque(maxlen=10)
        
        # 性能统计
        self.operation_times: Dict[str, List[float]] = {}
        self.operation_counts: Dict[str, int] = {}
        
        # 布局
        self.layout = Layout()
        self._setup_layout()
    
    def _setup_layout(self) -> None:
        """设置布局"""
        self.layout.split(
            Layout(name="header", size=5),
            Layout(name="main"),
            Layout(name="footer", size=8)
        )
        
        self.layout["main"].split_row(
            Layout(name="progress", ratio=3),
            Layout(name="info", ratio=2)
        )
    
    def add_task(
        self,
        task_type: TaskType,
        description: str,
        estimated_duration: Optional[float] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> str:
        """添加新任务"""
        self.task_counter += 1
        task_id = f"{task_type.value}_{self.task_counter}"
        
        task = TaskInfo(
            task_id=task_id,
            task_type=task_type,
            description=description,
            estimated_end_time=time.time() + estimated_duration if estimated_duration else None,
            details=details or {}
        )
        self.active_tasks[task_id] = task
        
        # 添加到进度条
        task.rich_task_id = self.progress.add_task(
            description=description,
            total=100.0,
            completed=0.0
        )
        
        self.last_events.append(f"开始任务: {description}")
        return task_id
    
    def update_task(
        self,
        task_id: str,
        progress: float,
        status: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        message: Optional[str] = None
    ) -> None:
        """更新任务进度"""
        if task_id not in self.active_tasks:
            return
        
        task = self.active_tasks[task_id]
        task.progress = progress
        if status:
            task.status = status
        if details:
            task.details.update(details)
        if message:
            task.status = message
        
        # 更新进度条
        if task.rich_task_id is not None:
            self.progress.update(task.rich_task_id, completed=progress * 100)
        
        # 更新预估时间
        if task.estimated_end_time is None and progress > 0.1:
            elapsed = time.time() - task.start_time
            estimated_total = elapsed / progress
            task.estimated_end_time = task.start_time + estimated_total
    
    def complete_task(self, task_id: str, result: Optional[str] = None) -> None:
        """完成任务"""
        if task_id not in self.active_tasks:
            return
        
        task = self.active_tasks[task_id]
        task.progress = 1.0
        task.status = "已完成"
        
        # 记录操作时间
        duration = time.time() - task.start_time
        task_type_name = task.task_type.value
        if task_type_name not in self.operation_times:
            self.operation_times[task_type_name] = []
        self.operation_times[task_type_name].append(duration)
        
        # 记录操作次数
        if task_type_name not in self.operation_counts:
            self.operation_counts[task_type_name] = 0
        self.operation_counts[task_type_name] += 1
        
        # 更新进度条
        if task.rich_task_id is not None:
            self.progress.update(task.rich_task_id, completed=100.0)
        
        # 移动到已完成任务
        self.completed_tasks.append(task)
        del self.active_tasks[task_id]
        
        self.last_events.append(f"完成任务: {task.description}")
    
    def fail_task(self, task_id: str, error: str) -> None:
        """任务失败"""
        if task_id not in self.active_tasks:
            return
        
        task = self.active_tasks[task_id]
        task.status = f"失败: {error}"
        
        # 更新进度条
        if task.rich_task_id is not None:
            self.progress.update(task.rich_task_id, completed=task.progress * 100)
        
        # 移动到已完成任务
        self.completed_tasks.append(task)
        del self.active_tasks[task_id]
        
        self.last_events.append(f"任务失败: {task.description} - {error}")
    
    def set_state(self, state: str, operation: str) -> None:
        """设置当前状态和操作"""
        self.current_state = state
        self.current_operation = operation
    
    def on_event(self, event: Dict[str, Any]) -> None:
        """处理事件"""
        event_type = event.get("event", "")
        event_data = event.get("data", {})
        
        if event_type == "llm_request":
            self.add_task(
                task_type=TaskType.LLM_REQUEST,
                description="LLM 请求处理",
                estimated_duration=10.0,  # 基于历史数据估算
                details={"messages": event_data.get("messages", 0)}
            )
        elif event_type == "llm_response":
            # 完成最新的 LLM 任务
            llm_tasks = [t for t in self.active_tasks.values() if t.task_type == TaskType.LLM_REQUEST]
            if llm_tasks:
                self.complete_task(llm_tasks[-1].task_id)
        elif event_type == "file_read":
            path = event_data.get("path", "")
            self.add_task(
                task_type=TaskType.FILE_READ,
                description=f"读取文件: {path}",
                estimated_duration=2.0,
                details={"path": path}
            )
        elif event_type == "file_read_complete":
            read_tasks = [t for t in self.active_tasks.values() if t.task_type == TaskType.FILE_READ]
            if read_tasks:
                self.complete_task(read_tasks[-1].task_id)
        elif event_type == "file_write":
            path = event_data.get("path", "")
            self.add_task(
                task_type=TaskType.FILE_WRITE,
                description=f"写入文件: {path}",
                estimated_duration=1.5,
                details={"path": path}
            )
        elif event_type == "file_write_complete":
            write_tasks = [t for t in self.active_tasks.values() if t.task_type == TaskType.FILE_WRITE]
            if write_tasks:
                self.complete_task(write_tasks[-1].task_id)
        elif event_type == "search":
            pattern = event_data.get("pattern", "")
            self.add_task(
                task_type=TaskType.SEARCH,
                description=f"搜索: {pattern}",
                estimated_duration=5.0,
                details={"pattern": pattern}
            )
        elif event_type == "search_complete":
            search_tasks = [t for t in self.active_tasks.values() if t.task_type == TaskType.SEARCH]
            if search_tasks:
                self.complete_task(search_tasks[-1].task_id)
        elif event_type == "command_exec":
            command = event_data.get("command", "")
            self.add_task(
                task_type=TaskType.COMMAND_EXEC,
                description=f"执行命令: {command}",
                estimated_duration=8.0,
                details={"command": command}
            )
        elif event_type == "command_complete":
            cmd_tasks = [t for t in self.active_tasks.values() if t.task_type == TaskType.COMMAND_EXEC]
            if cmd_tasks:
                self.complete_task(cmd_tasks[-1].task_id)
        
        self.last_events.append(f"{event_type}: {event_data}")
    
    def render(self) -> Layout:
        """渲染完整界面"""
        # 更新布局
        self.layout["header"].update(self._render_header())
        self.layout["progress"].update(self._render_progress())
        self.layout["info"].update(self._render_info())
        self.layout["footer"].update(self._render_footer())
        
        return self.layout
    
    def _render_header(self) -> Panel:
        """渲染头部面板"""
        elapsed = int(time.time() - self.start_time)
        
        status_table = Table(show_header=False, box=None, pad_edge=False)
        status_table.add_column(justify="left", style="bold", width=12)
        status_table.add_column(justify="left")
        
        status_table.add_row("状态:", self.current_state)
        status_table.add_row("当前操作:", self.current_operation)
        status_table.add_row("运行时间:", f"{elapsed}秒")
        status_table.add_row("活跃任务:", str(len(self.active_tasks)))
        
        return Panel(status_table, title="系统状态", border_style="blue")
    
    def _render_progress(self) -> Panel:
        """渲染进度面板"""
        return Panel(
            self.progress,
            title="任务进度",
            border_style="green"
        )
    
    def _render_info(self) -> Panel:
        """渲染信息面板"""
        # 创建性能统计表格
        perf_table = Table(show_header=True, box=None, title="性能统计")
        perf_table.add_column("操作类型", style="bold")
        perf_table.add_column("次数", justify="right")
        perf_table.add_column("平均耗时", justify="right")
        perf_table.add_column("总耗时", justify="right")
        
        for op_type, count in self.operation_counts.items():
            if op_type in self.operation_times:
                times = self.operation_times[op_type]
                avg_time = sum(times) / len(times)
                total_time = sum(times)
                perf_table.add_row(
                    op_type,
                    str(count),
                    f"{avg_time:.2f}s",
                    f"{total_time:.2f}s"
                )
        
        # 创建已完成任务表格
        completed_table = Table(show_header=True, box=None, title="最近完成的任务")
        completed_table.add_column("任务", style="bold")
        completed_table.add_column("耗时", justify="right")
        completed_table.add_column("状态")
        
        for task in reversed(list(self.completed_tasks)):
            duration = time.time() - task.start_time
            completed_table.add_row(
                task.description[:30] + "..." if len(task.description) > 30 else task.description,
                f"{duration:.2f}s",
                task.status
            )
        
        # 组合表格
        return Panel(
            Group(perf_table, completed_table),
            title="详细信息",
            border_style="cyan"
        )
    
    def _render_footer(self) -> Panel:
        """渲染底部面板"""
        # 创建事件历史表格
        events_table = Table(show_header=False, box=None)
        events_table.add_column("时间", style="dim", width=8)
        events_table.add_column("事件")
        
        for event in reversed(list(self.last_events)):
            events_table.add_row(
                time.strftime("%H:%M:%S"),
                event[:60] + "..." if len(event) > 60 else event
            )
        
        return Panel(
            events_table,
            title="事件历史",
            border_style="yellow"
        )
    
    def on_task_progress(self, task_progress: TaskProgress) -> None:
        """处理任务进度更新（来自 AsyncTaskManager）"""
        # 根据任务ID查找对应的任务
        task = None
        for t in self.active_tasks.values():
            if t.task_id == task_progress.task_id:
                task = t
                break
        
        if task:
            self.update_task(
                task.task_id,
                progress=task_progress.progress,
                status=task_progress.message,
                details=task_progress.details
            )


class SimpleProgressDisplay:
    """简化的进度显示，用于非 Live 模式"""
    
    def __init__(self, console: Console):
        self.console = console
        self.active_tasks: Dict[str, TaskInfo] = {}
        self.task_counter = 0
        self.last_event_time = time.time()
    
    def add_task(
        self,
        task_type: TaskType,
        description: str,
        estimated_duration: Optional[float] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> str:
        """添加新任务"""
        self.task_counter += 1
        task_id = f"{task_type.value}_{self.task_counter}"
        
        task = TaskInfo(
            task_id=task_id,
            task_type=task_type,
            description=description,
            estimated_end_time=time.time() + estimated_duration if estimated_duration else None,
            details=details or {}
        )
        self.active_tasks[task_id] = task
        
        self.console.print(f"[dim]→ {description}[/dim]")
        return task_id
    
    def update_task(
        self,
        task_id: str,
        progress: float,
        status: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        message: Optional[str] = None
    ) -> None:
        """更新任务进度"""
        if task_id not in self.active_tasks:
            return
        
        task = self.active_tasks[task_id]
        if message and time.time() - self.last_event_time > 1.0:  # 限制输出频率
            self.console.print(f"[dim]  {message} ({progress*100:.1f}%)[/dim]")
            self.last_event_time = time.time()
    
    def complete_task(self, task_id: str, result: Optional[str] = None) -> None:
        """完成任务"""
        if task_id not in self.active_tasks:
            return
        
        task = self.active_tasks[task_id]
        duration = time.time() - task.start_time
        self.console.print(f"[green]✓ {task.description}[/green] [dim]({duration:.2f}s)[/dim]")
        del self.active_tasks[task_id]
    
    def fail_task(self, task_id: str, error: str) -> None:
        """任务失败"""
        if task_id not in self.active_tasks:
            return
        
        task = self.active_tasks[task_id]
        self.console.print(f"[red]✗ {task.description}: {error}[/red]")
        del self.active_tasks[task_id]
    
    def print_event(self, event: str) -> None:
        """打印事件"""
        self.console.print(f"[dim]• {event}[/dim]")