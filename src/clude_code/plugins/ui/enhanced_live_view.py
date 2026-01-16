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
        
        # Claude Code 风格：状态 + 左侧滚动输出 + 右侧操作面板
        self.current_state = "IDLE"
        self.current_operation = "等待中"
        self.last_events: deque[str] = deque(maxlen=12)
        self.conversation_lines: deque[str] = deque(maxlen=22)

        # 快照（用于右侧面板）
        self.last_step: int | str = "-"
        self.last_event: str = "等待"
        self.last_tool: dict[str, Any] = {}
        self.last_tool_result: dict[str, Any] = {}
        self.last_llm_req: dict[str, Any] = {}
        self.last_llm_resp: dict[str, Any] = {}
        self.llm_stats = {
            "prompt_tokens_est": 0,
            "completion_tokens_est": 0,
            "tps": 0.0,
        }

        # 当前“正在进行的任务”ID（用于 tool_result 时完成）
        self._current_task_id: str | None = None
        
        # 性能统计
        self.operation_times: Dict[str, List[float]] = {}
        self.operation_counts: Dict[str, int] = {}
        
        # 布局
        self.layout = Layout()
        self._setup_layout()
    
    def _setup_layout(self) -> None:
        """设置布局"""
        # Claude Code 风格：左侧滚动输出 + 右侧状态/操作；底部事件
        self.layout.split(
            Layout(name="header", size=4),
            Layout(name="main"),
            Layout(name="footer", size=7),
        )

        self.layout["main"].split_row(
            Layout(name="conversation", ratio=3),
            Layout(name="side", ratio=2),
        )

        self.layout["side"].split(
            Layout(name="status", size=8),
            Layout(name="ops", size=10), # 调整 ops 区域大小以容纳 LLM stats
            Layout(name="llm_stats_panel", ratio=1), # 新增 LLM 统计面板
        )

    def _push_line(self, s: str) -> None:
        s = (s or "").strip()
        if not s:
            return
        # 控制长度，避免撑爆终端
        if len(s) > 220:
            s = s[:219] + "…"
        self.conversation_lines.append(s)

    def _push_block(self, title: str, lines: list[str] | None = None, *, color: str = "cyan") -> None:
        """
        Claude Code 风格的“阶段块”输出：用边界 + 缩进让阶段与信息更可读。
        """
        title = (title or "").strip()
        if not title:
            return
        self._push_line(f"[{color}]┌─ {title}[/{color}]")
        for ln in (lines or []):
            ln = (ln or "").strip()
            if not ln:
                continue
            self._push_line(f"[{color}]│[/{color}] {ln}")
        self._push_line(f"[{color}]└─[/{color}]")
    
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
        self.last_step = event.get("step", self.last_step)
        event_type = str(event.get("event", ""))
        event_data = event.get("data", {}) or {}
        self.last_event = event_type

        # 记录事件历史（更像 Claude Code 的“事件轨迹”）
        self.last_events.append(f"{event_type}: {str(event_data)[:200]}")

        # --- 状态机事件 ---
        if event_type == "state":
            st = str(event_data.get("state", ""))
            if st:
                self.current_state = st
                self.current_operation = str(event_data.get("reason") or event_data.get("step") or "运行中")
            return

        if event_type == "project_memory":
            loaded = bool(event_data.get("loaded"))
            path = str(event_data.get("path", ""))
            truncated = bool(event_data.get("truncated", False))
            length = event_data.get("length")
            legacy = bool(event_data.get("legacy_name", False))
            if loaded:
                self._push_block(
                    "项目记忆已加载（CLUDE.md）",
                    [f"path={path}", f"length={length}", f"truncated={truncated}", f"legacy_name={legacy}"],
                    color="cyan",
                )
            else:
                self._push_block(
                    "未加载项目记忆（CLUDE.md）",
                    [f"path={path}", "原因：文件不存在/为空/读取失败"],
                    color="cyan",
                )
            return

        # --- 规划阶段 ---
        if event_type == "planning_llm_request":
            attempt = event_data.get("attempt")
            self._push_block("规划中", [f"尝试次数: {attempt}"], color="magenta")
            return

        if event_type == "plan_generated":
            title = str(event_data.get("title", "")).strip()
            steps = event_data.get("steps")
            lines: list[str] = []
            if title:
                lines.append(f"[bold]目标[/bold]: {title}")
            if steps is not None:
                lines.append(f"[bold]步骤数[/bold]: {steps}")
            self._push_block("计划已生成", lines, color="magenta")
            return

        if event_type == "plan_parse_failed":
            attempt = event_data.get("attempt")
            err = str(event_data.get("error", ""))[:200]
            self._push_block("计划解析失败", [f"attempt={attempt}", f"[red]{err}[/red]"], color="red")
            return

        if event_type == "plan_step_start":
            step_id = event_data.get("step_id")
            idx = event_data.get("idx")
            total = event_data.get("total")
            self.current_operation = f"执行步骤 {idx}/{total}: {step_id}"
            self._push_block("执行步骤开始", [f"{idx}/{total}  step_id={step_id}"], color="yellow")
            return

        if event_type == "plan_step_blocked":
            step_id = event_data.get("step_id")
            unmet = event_data.get("unmet_deps")
            self._push_block("步骤被阻塞", [f"step_id={step_id}", f"unmet_deps={unmet}"], color="yellow")
            return

        if event_type == "plan_step_done":
            step_id = event_data.get("step_id")
            self._push_block("步骤完成", [f"step_id={step_id}"], color="green")
            return

        if event_type == "plan_step_replan_requested":
            step_id = event_data.get("step_id")
            self._push_block("请求重规划", [f"step_id={step_id}"], color="yellow")
            return

        if event_type == "replan_generated":
            title = str(event_data.get("title", "")).strip()
            steps = event_data.get("steps")
            replans_used = event_data.get("replans_used")
            lines = []
            if title:
                lines.append(f"[bold]新计划[/bold]: {title}")
            if steps is not None:
                lines.append(f"[bold]步骤数[/bold]: {steps}")
            if replans_used is not None:
                lines.append(f"[bold]已用重规划[/bold]: {replans_used}")
            self._push_block("重规划生成", lines, color="magenta")
            return

        # --- 对话/输出 ---
        if event_type == "user_message":
            txt = str(event_data.get("text", "")).strip()
            if txt:
                self._push_line(f"[bold blue]you[/bold blue]: {txt}")
            return

        if event_type == "display":
            content = str(event_data.get("content", "")).strip()
            level = str(event_data.get("level", "info"))
            title = event_data.get("title")
            prefix = f"[{title}] " if title else ""
            color = {"info": "cyan", "success": "green", "warning": "yellow", "error": "red", "progress": "blue"}.get(level, "cyan")
            for ln in (content.splitlines()[:6] if content else []):
                self._push_line(f"[{color}]agent[/{color}]: {prefix}{ln}")
            return

        # --- LLM 事件 ---
        if event_type == "llm_request":
            self.current_operation = "LLM 请求"
            self.last_llm_req = {"messages": event_data.get("messages"), "step_id": event_data.get("step_id")}
            self._current_task_id = self.add_task(TaskType.LLM_REQUEST, "LLM 请求", estimated_duration=10.0, details=self.last_llm_req)
            self._push_line("[dim]🤖 LLM 请求中...[/dim]")
            return

        if event_type == "llm_request_params":
            # 来自 llm_io.py：包含 model/base_url/api_mode/messages_count 等摘要
            self.last_llm_req = dict(event_data) if isinstance(event_data, dict) else {"raw": str(event_data)[:200]}
            model = str(self.last_llm_req.get("model", "auto"))
            api_mode = str(self.last_llm_req.get("api_mode", ""))
            msg_n = self.last_llm_req.get("messages_count")
            self._push_line(f"[dim]LLM params: model={model} api={api_mode} messages={msg_n}[/dim]")
            return

        if event_type == "llm_response":
            txt = str(event_data.get("text", "")).strip()
            self.last_llm_resp = {"text_preview": txt[:240], "truncated": bool(event_data.get("truncated", False))}
            # 完成 LLM 任务
            if self._current_task_id:
                self.complete_task(self._current_task_id)
                self._current_task_id = None
            # 展示一小段（更像 Claude Code：让用户看到模型在输出什么）
            if txt:
                self._push_line(f"[bold magenta]assistant[/bold magenta]: {txt.splitlines()[0][:200]}")
            return

        if event_type == "llm_response_data":
            # 来自 llm_io.py：text_length/text_preview 等摘要
            self.last_llm_resp = dict(event_data) if isinstance(event_data, dict) else {"raw": str(event_data)[:200]}
            tl = self.last_llm_resp.get("text_length")
            self._push_line(f"[dim]LLM resp: text_length={tl}[/dim]")
            return
        
        if event_type == "llm_usage":
            prompt_tokens = event_data.get("prompt_tokens_est", 0)
            completion_tokens = event_data.get("completion_tokens_est", 0)
            elapsed_ms = event_data.get("elapsed_ms", 0)
            
            self.llm_stats["prompt_tokens_est"] += prompt_tokens
            self.llm_stats["completion_tokens_est"] += completion_tokens
            
            tps = 0.0
            if elapsed_ms > 0:
                tps = (completion_tokens / elapsed_ms) * 1000
            self.llm_stats["tps"] = tps

            self._push_line(
                f"[dim]LLM usage: prompt_tokens={prompt_tokens} completion_tokens={completion_tokens} "
                f"elapsed={elapsed_ms}ms tps={tps:.1f}[/dim]"
            )
            return


        # --- 工具事件（Claude Code 核心体验：工具调用与结果） ---
        if event_type == "tool_call_parsed":
            tool = str(event_data.get("tool", ""))
            args = event_data.get("args", {}) or {}
            self.last_tool = {"tool": tool, "args": args}
            self.current_operation = f"工具: {tool}"

            # 将 tool 映射到任务类型（基于工具名的最小映射）
            if tool in {"read_file", "list_dir"}:
                ttype = TaskType.FILE_READ
            elif tool in {"write_file"}:
                ttype = TaskType.FILE_WRITE
            elif tool in {"apply_patch", "undo_patch"}:
                ttype = TaskType.PATCHING
            elif tool in {"grep", "glob_file_search", "search_semantic"}:
                ttype = TaskType.SEARCH
            elif tool in {"run_cmd"}:
                ttype = TaskType.COMMAND_EXEC
            else:
                ttype = TaskType.SEARCH

            # 生成简短参数摘要
            if isinstance(args, dict):
                key_order = ["path", "pattern", "query", "command"]
                summary_parts = []
                for k in key_order:
                    if k in args:
                        summary_parts.append(f"{k}={str(args.get(k))[:80]}")
                if not summary_parts:
                    summary_parts = [f"{k}={str(v)[:60]}" for k, v in list(args.items())[:2]]
                args_summary = " ".join(summary_parts)
            else:
                args_summary = str(args)[:120]

            self._current_task_id = self.add_task(ttype, f"{tool} {args_summary}".strip(), estimated_duration=4.0, details={"tool": tool})
            self._push_line(f"[bold yellow]tool[/bold yellow]: {tool} {args_summary}".strip())
            return

        if event_type == "tool_result":
            tool = str(event_data.get("tool", ""))
            ok = bool(event_data.get("ok"))
            err = event_data.get("error")
            payload = event_data.get("payload") or {}
            self.last_tool_result = {"tool": tool, "ok": ok, "error": err, "payload_keys": list(payload.keys()) if isinstance(payload, dict) else []}

            if self._current_task_id:
                if ok:
                    self.complete_task(self._current_task_id)
                else:
                    self.fail_task(self._current_task_id, str(err)[:160])
                self._current_task_id = None

            if ok:
                # 更像 Claude Code：为关键工具做语义摘要
                summary = ""
                if tool == "grep" and isinstance(payload, dict):
                    hits = payload.get("hits") or []
                    engine = payload.get("engine")
                    truncated = payload.get("truncated")
                    if isinstance(hits, list):
                        summary = f"hits={len(hits)} engine={engine} truncated={truncated}"
                elif tool == "read_file" and isinstance(payload, dict):
                    summary = f"path={payload.get('path')} read={payload.get('read_size')}B/{payload.get('total_size')}B truncated={payload.get('truncated')}"
                    if payload.get("offset") is not None or payload.get("limit") is not None:
                        summary += f" slice=offset={payload.get('offset')} limit={payload.get('limit')}"
                elif tool == "run_cmd" and isinstance(payload, dict):
                    summary = f"exit_code={payload.get('exit_code')} cwd={payload.get('cwd')}"
                elif tool == "apply_patch" and isinstance(payload, dict):
                    summary = f"path={payload.get('path')} replacements={payload.get('replacements')} undo_id={payload.get('undo_id')}"
                elif tool == "undo_patch" and isinstance(payload, dict):
                    summary = f"path={payload.get('path')} undo_id={payload.get('undo_id')}"
                elif tool == "display" and isinstance(payload, dict):
                    summary = f"level={payload.get('level')} truncated={payload.get('truncated')}"

                line = f"[green]✓[/green] {tool} ok"
                if summary:
                    line += f" ({summary})"
                self._push_line(line)
            else:
                self._push_line(f"[red]✗[/red] {tool} err={str(err)[:160]}")
            return

        # --- 验证阶段 ---
        if event_type == "autofix_check":
            ok = bool(event_data.get("ok"))
            summary = str(event_data.get("summary", "")).strip()
            color = "green" if ok else "yellow"
            self._push_block("自动验证", [f"ok={ok}", summary[:240]], color=color)
            return

        if event_type == "final_verify":
            ok = bool(event_data.get("ok"))
            vtype = event_data.get("type")
            summary = str(event_data.get("summary", "")).strip()
            color = "green" if ok else "red"
            self._push_block("最终验证", [f"ok={ok} type={vtype}", summary[:240]], color=color)
            return

        if event_type == "stop_reason":
            reason = str(event_data.get("reason", "")).strip()
            self._push_block("提前停止", [f"reason={reason}", str(event_data)[:240]], color="red")
            return
    
    def render(self) -> Layout:
        """渲染完整界面"""
        # 更新布局
        self.layout["header"].update(self._render_header())
        self.layout["conversation"].update(self._render_conversation())
        self.layout["status"].update(self._render_status())
        self.layout["ops"].update(self._render_ops())
        self.layout["llm_stats_panel"].update(self._render_llm_stats_panel()) # 渲染 LLM 统计面板
        self.layout["footer"].update(self._render_footer())
        
        return self.layout
    
    def _render_header(self) -> Panel:
        """渲染头部面板"""
        elapsed = int(time.time() - self.start_time)
        
        status_table = Table(show_header=False, box=None, pad_edge=False)
        status_table.add_column(justify="left", style="bold", width=12)
        status_table.add_column(justify="left")
        
        status_table.add_row("模式:", "Clude Code 风格（enhanced）")
        status_table.add_row("状态:", self.current_state)
        status_table.add_row("操作:", self.current_operation)
        status_table.add_row("运行:", f"{elapsed}s  step={self.last_step}  ev={self.last_event}")

        return Panel(status_table, title="clude chat", border_style="blue")
    
    def _render_conversation(self) -> Panel:
        """左侧：滚动输出（更接近 Claude Code）"""
        if not self.conversation_lines:
            body = Text("（等待输出…）", style="dim")
        else:
            body = Text()
            for ln in list(self.conversation_lines)[-22:]:
                body.append(Text.from_markup(ln))
                body.append("\n")
        return Panel(body, title="对话 / 输出", border_style="cyan")
    
    def _render_status(self) -> Panel:
        """右侧上：状态与环境摘要"""
        t = Table(show_header=False, box=None, pad_edge=False)
        t.add_column(justify="left", style="bold", width=10)
        t.add_column(justify="left")
        t.add_row("模型", str(getattr(self.cfg.llm, "model", "") or "auto")[:40])
        t.add_row("地址", str(getattr(self.cfg.llm, "base_url", ""))[:60])
        t.add_row("状态", self.current_state)
        t.add_row("步骤", str(self.last_step))
        t.add_row("事件", self.last_event)
        t.add_row("任务", f"{len(self.active_tasks)} 活跃 / {len(self.completed_tasks)} 最近完成")
        return Panel(t, title="状态", border_style="blue")

    def _render_llm_stats_panel(self) -> Panel:
        """渲染 LLM 统计信息面板"""
        t = Table(show_header=False, box=None, pad_edge=False)
        t.add_column(justify="left", style="bold", width=12)
        t.add_column(justify="left")

        t.add_row("Prompt Tokens:", f"{self.llm_stats['prompt_tokens_est']}")
        t.add_row("Output Tokens:", f"{self.llm_stats['completion_tokens_est']}")
        t.add_row("Output TPS:", f"{self.llm_stats['tps']:.1f}")

        return Panel(t, title="LLM 用量 (估算)", border_style="magenta")
    
    def _render_ops(self) -> Panel:
        """右侧下：最近一次工具/模型快照 + 任务进度条"""
        snap = Table(show_header=False, box=None, pad_edge=False)
        snap.add_column(justify="left", style="bold", width=10)
        snap.add_column(justify="left")

        tool = self.last_tool.get("tool")
        if tool:
            snap.add_row("工具", str(tool))
        if self.last_tool_result:
            snap.add_row("结果", f"ok={self.last_tool_result.get('ok')} keys={self.last_tool_result.get('payload_keys', [])[:6]}")
        if self.last_llm_req:
            snap.add_row("LLM", f"messages={self.last_llm_req.get('messages_count')} step_id={self.last_llm_req.get('step_id')}")

        grp = Group(snap, Text(""), self.progress)
        return Panel(grp, title="操作面板", border_style="green")
    
    def _render_footer(self) -> Panel:
        """渲染底部面板"""
        events_table = Table(show_header=False, box=None, pad_edge=False)
        events_table.add_column("最近事件", style="dim")
        for ev in reversed(list(self.last_events)[-12:]):
            events_table.add_row(ev[:180] + ("…" if len(ev) > 180 else ""))
        return Panel(events_table, title="事件", border_style="yellow")
    
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