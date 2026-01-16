"""
Textual-based TUI（对标 OpenCode）：
- 多窗格布局（左侧输出/右侧状态与操作/底部事件）
- 每个窗格可滚动（支持鼠标滚轮查看历史）
- 不依赖 rich.Live 的整屏刷新

注意：该模块依赖可选依赖 `textual`（见 pyproject.toml 的 [project.optional-dependencies].ui）。
未安装时应由调用方优雅降级。
"""

from __future__ import annotations

from queue import Empty, Queue
from threading import Thread
from typing import Any, Callable
import json
from rich.text import Text
from rich.table import Table
from collections import deque


def run_opencode_tui(
    *,
    cfg: Any,
    run_turn: Callable[[str, Callable[[str], bool], Callable[[dict[str, Any]], None]], None],
) -> None:
    """
    运行 OpenCode 风格 Textual TUI（在主线程阻塞运行）。

    为什么这样做：
    - Textual/TUI 框架通常需要在主线程运行（才能正确处理输入/鼠标/终端能力）
    - AgentLoop 在后台线程执行，通过队列把事件推送回 UI 线程渲染
    """

    # 延迟导入：避免纯 CLI/doctor/tools 也被迫安装 textual
    # 可选依赖：Textual（运行时存在即可；静态检查允许缺失）
    from textual.app import App, ComposeResult  # type: ignore[import-not-found]
    from textual.containers import Horizontal, Vertical  # type: ignore[import-not-found]
    from textual.widgets import Footer, Header, Input, RichLog  # type: ignore[import-not-found]

    q: Queue[dict[str, Any]] = Queue(maxsize=50_000)

    class _Log(RichLog):
        """RichLog 默认可滚动，支持鼠标滚轮查看历史。"""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            kwargs.setdefault("wrap", True)
            super().__init__(*args, **kwargs)
            # 默认跟随尾部（更像 OpenCode）；用户可按 f 切换“浏览历史/跟随输出”
            self.auto_scroll = True

    class OpencodeTUI(App):
        TITLE = "clude chat"
        SUB_TITLE = "opencode"
        CSS = """
        Screen { layout: vertical; }
        #main { height: 1fr; }
        /* 顶部 clude chat 面板：按内容自适应，避免多余空白 */
        #header_panel { height: auto; min-height: 3; }
        #left { width: 3fr; }
        #right { width: 2fr; }
        /* 输入框：需要给边框/提示留空间，否则会导致无法输入或不可见 */
        #input_row { height: 3; min-height: 3; }
        /* 事件区：稍微收紧，给主内容更多空间 */
        #events { height: 8; }
        _Log { border: solid $primary; }
        /* 所有小窗口标题居中（对齐你的要求） */
        #header_panel, #conversation, #status, #ops, #events, #input { border-title-align: center; }
        /* 右侧：状态按内容自适应，操作面板吃掉剩余高度 */
        #status { height: auto; }
        #ops { height: 1fr; min-height: 8; }
        """

        BINDINGS = [
            ("q", "quit", "Quit"),
            ("ctrl+c", "quit", "Quit"),
            ("f", "toggle_follow", "Follow/Scroll"),
            ("end", "jump_bottom", "Bottom"),
        ]

        def __init__(self) -> None:
            super().__init__()
            self._busy = False
            self._follow = True
            self._model = str(getattr(getattr(cfg, "llm", None), "model", "") or "auto")
            self._base_url = str(getattr(getattr(cfg, "llm", None), "base_url", "") or "")

            # 对齐 enhanced 的“状态/操作”字段
            self._state = "IDLE"
            self._operation = "等待中"
            self._last_step: int | str = "-"
            self._last_event: str = "waiting"
            self._last_llm_messages: int | None = None
            self._last_tool: str | None = None
            self._last_tool_args: str | None = None
            self._last_tool_result: str | None = None
            self._active_tasks: int = 0
            self._recent_completed: deque[str] = deque(maxlen=5)
            self._project_memory_shown: bool = False

            self._max_tokens = int(getattr(getattr(cfg, "llm", None), "max_tokens", 0) or 0)
            self._llm_prompt = 0
            self._llm_completion = 0
            self._tps = 0.0

        def compose(self) -> ComposeResult:
            yield Header(show_clock=True)
            yield _Log(id="header_panel")
            with Horizontal(id="main"):
                with Vertical(id="left"):
                    yield _Log(id="conversation")
                with Vertical(id="right"):
                    yield _Log(id="status")
                    yield _Log(id="ops")
            with Horizontal(id="input_row"):
                yield Input(placeholder="输入内容，回车发送（q 退出）", id="input")
            yield _Log(id="events")
            yield Footer()

        def on_mount(self) -> None:
            # 为每个“窗口”设置边框标题（对齐 enhanced 的分区命名）
            header_panel = self.query_one("#header_panel", _Log)
            conversation = self.query_one("#conversation", _Log)
            status_panel = self.query_one("#status", _Log)
            ops_panel = self.query_one("#ops", _Log)
            events_panel = self.query_one("#events", _Log)
            input_box = self.query_one("#input", Input)

            header_panel.border_title = "clude chat"
            conversation.border_title = "对话/输出"
            status_panel.border_title = "状态"
            ops_panel.border_title = "操作面板"
            events_panel.border_title = "事件"
            input_box.border_title = "you"

            # 标题居中（Textual 支持 border_title_align）
            for w in (header_panel, conversation, status_panel, ops_panel, events_panel, input_box):
                try:
                    w.border_title_align = "center"  # type: ignore[attr-defined]
                except Exception:
                    pass

            # 确保输入框可用且默认获得焦点
            try:
                input_box.focus()
            except Exception:
                pass

            # 初始状态：进入界面即“等待输入”，不要沿用上次的 DONE/执行态
            self._state = "IDLE"
            self._operation = "等待中"
            self._last_step = "-"
            self._last_event = "ready"
            self._active_tasks = 0
            self._recent_completed.clear()

            # 进入界面即输出项目记忆加载块（对齐 enhanced：无需等到第一轮 run_turn）
            try:
                from clude_code.orchestrator.agent_loop.prompts import load_project_memory

                _txt, meta = load_project_memory(getattr(cfg, "workspace_root", "."))
                loaded = bool(meta.get("loaded"))
                path = str(meta.get("path", ""))
                truncated = bool(meta.get("truncated", False))
                length = meta.get("length")
                legacy = bool(meta.get("legacy_name", False))
                if loaded:
                    conversation.write(Text("┌─ 项目记忆已加载（CLUDE.md）", style="cyan"))
                    conversation.write(Text(f"│ path={path}", style="cyan"))
                    conversation.write(Text(f"│ length={length}", style="cyan"))
                    conversation.write(Text(f"│ truncated={truncated}", style="cyan"))
                    conversation.write(Text(f"│ legacy_name={legacy}", style="cyan"))
                    conversation.write(Text("└─", style="cyan"))
                else:
                    conversation.write(Text("┌─ 未加载项目记忆（CLUDE.md）", style="cyan"))
                    conversation.write(Text(f"│ path={path}", style="cyan"))
                    conversation.write(Text("│ 原因：文件不存在/为空/读取失败", style="cyan"))
                    conversation.write(Text("└─", style="cyan"))
                self._project_memory_shown = True
            except Exception:
                # 失败不阻塞 UI
                pass

            self._refresh_header_panel()
            self._refresh_status()
            self._refresh_ops()

            self.query_one("#events", _Log).write(
                "[dim]提示：滚轮可滚动历史；按 f 切换跟随输出；按 End 回到底部。[/dim]"
            )
            self.set_interval(0.05, self._drain_events)

        def _refresh_header_panel(self) -> None:
            """顶部 `clude chat` 窗口：承载 enhanced 顶栏里的关键运行态信息。"""
            hp = self.query_one("#header_panel", _Log)
            hp.clear()

            # 第一行：对齐 enhanced（模式/状态/操作/运行信息横向排布）
            row1 = Table.grid(expand=True)
            row1.add_column(justify="left", ratio=5, no_wrap=True)
            row1.add_column(justify="left", ratio=2, no_wrap=True)
            row1.add_column(justify="left", ratio=3, no_wrap=True)
            row1.add_column(justify="right", ratio=4, no_wrap=True)

            t_mode = Text("模式: Clude Code 风格（opencode）")
            t_state = Text(f"状态: {self._state}")
            t_op = Text(f"操作: {self._operation}")
            t_run = Text(f"运行: step={self._last_step}  ev={self._last_event}", style="dim")

            row1.add_row(t_mode, t_state, t_op, t_run)
            hp.write(row1)

            # 第二行：Context/Output/TPS
            hp.write(Text(f"  {self._render_top_metrics()}", style="dim"))

        def _refresh_status(self) -> None:
            """右侧“状态”窗格：保留环境/模型信息，避免与顶部重复。"""
            status = self.query_one("#status", _Log)
            status.clear()
            t = Table(show_header=False, box=None, pad_edge=False)
            t.add_column(justify="left", style="bold", width=6)
            t.add_column(justify="left")

            t.add_row("模型", self._model[:48])
            if self._base_url:
                t.add_row("地址", self._base_url[:80])
            t.add_row("状态", str(self._state))
            t.add_row("步骤", str(self._last_step))
            t.add_row("事件", str(self._last_event))
            t.add_row("任务", f"{self._active_tasks} 活跃 / {len(self._recent_completed)} 最近完成")
            status.write(t)

        def _refresh_ops(self) -> None:
            """刷新右侧“操作面板”窗格（对齐 enhanced 的快照信息）。"""
            ops = self.query_one("#ops", _Log)
            ops.clear()
            if self._last_llm_messages is not None:
                ops.write(Text(f"LLM: messages={self._last_llm_messages}", style="dim"))
            if self._last_tool:
                args = f" {self._last_tool_args}" if self._last_tool_args else ""
                t = Text()
                t.append("tool: ", style="bold yellow")
                t.append(f"{self._last_tool}{args}")
                ops.write(t)
            if self._last_tool_result:
                ops.write(self._last_tool_result)
            if self._busy:
                ops.write(Text("…执行中（opencode TUI）", style="dim"))

        def _set_follow(self, follow: bool) -> None:
            self._follow = bool(follow)
            for wid in ("#conversation", "#status", "#ops", "#events"):
                try:
                    self.query_one(wid, _Log).auto_scroll = self._follow
                except Exception:
                    pass

        def action_toggle_follow(self) -> None:
            self._set_follow(not self._follow)
            self.query_one("#events", _Log).write(
                f"[dim]follow={'on' if self._follow else 'off'}[/dim]"
            )

        def action_jump_bottom(self) -> None:
            # 回到底部并开启 follow
            self._set_follow(True)
            for wid in ("#conversation", "#status", "#ops", "#events"):
                try:
                    self.query_one(wid, _Log).scroll_end(animate=False)
                except Exception:
                    pass

        def _render_top_metrics(self) -> str:
            if self._max_tokens > 0:
                pct = (self._llm_prompt / self._max_tokens) * 100 if self._max_tokens else 0.0
                ctx = f"Context: {self._llm_prompt}/{self._max_tokens} ({pct:.0f}%)"
            else:
                ctx = f"Context: {self._llm_prompt}"
            return f"{ctx}    Output: {self._llm_completion}/∞    {self._tps:.1f} tokens/sec"

        def _append_event_line(self, et: str, data: dict[str, Any]) -> None:
            events = self.query_one("#events", _Log)
            # Textual 窗格可滚动：这里尽量保留完整信息，但设置上限避免超长卡顿
            try:
                s = json.dumps(data, ensure_ascii=False, default=str)
            except Exception:
                s = str(data)
            if len(s) > 4000:
                s = s[:3999] + "…"
            t = Text()
            t.append(et, style="dim")
            t.append(" ")
            t.append(s)
            events.write(t)
            if self._follow:
                try:
                    events.scroll_end(animate=False)
                except Exception:
                    pass

        def _apply_event(self, ev: dict[str, Any]) -> None:
            et = str(ev.get("event", ""))
            data = ev.get("data", {}) or {}
            if "step" in ev and ev.get("step") is not None:
                self._last_step = ev.get("step")  # type: ignore[assignment]
            self._last_event = et or self._last_event

            conversation = self.query_one("#conversation", _Log)
            status = self.query_one("#status", _Log)
            ops = self.query_one("#ops", _Log)

            self._append_event_line(et, data)

            def _push_block(title: str, lines: list[str], *, color: str = "cyan") -> None:
                """在对话窗格输出 Claude Code 风格阶段块（对齐 enhanced 的视觉语言）。"""
                title = (title or "").strip()
                if not title:
                    return
                conversation.write(Text(f"┌─ {title}", style=color))
                for ln in lines:
                    ln = (ln or "").strip()
                    if not ln:
                        continue
                    conversation.write(Text(f"│ {ln}", style=color))
                conversation.write(Text("└─", style=color))
                if self._follow:
                    conversation.scroll_end(animate=False)

            # --- 状态机 ---
            if et == "state":
                st = str(data.get("state", "")).strip()
                if st:
                    self._state = st
                self._operation = str(data.get("reason") or data.get("step") or data.get("mode") or "运行中")
                self._active_tasks = 1 if self._busy else 0
                self._refresh_header_panel()
                self._refresh_status()
                return

            # 开场：项目记忆加载状态（对齐 enhanced 的“项目记忆已加载（CLUDE.md）”块）
            if et == "project_memory":
                # 已在 on_mount 输出过一次，避免用户输入后再次重复刷屏
                if self._project_memory_shown:
                    return
                loaded = bool(data.get("loaded"))
                path = str(data.get("path", ""))
                truncated = bool(data.get("truncated", False))
                length = data.get("length")
                legacy = bool(data.get("legacy_name", False))
                if loaded:
                    _push_block(
                        "项目记忆已加载（CLUDE.md）",
                        [
                            f"path={path}",
                            f"length={length}",
                            f"truncated={truncated}",
                            f"legacy_name={legacy}",
                        ],
                        color="cyan",
                    )
                else:
                    _push_block(
                        "未加载项目记忆（CLUDE.md）",
                        [f"path={path}", "原因：文件不存在/为空/读取失败"],
                        color="cyan",
                    )
                self._project_memory_shown = True
                return

            # 规划/执行阶段（对齐 enhanced）
            if et == "plan_step_start":
                idx = data.get("idx")
                total = data.get("total")
                step_id = data.get("step_id")
                self._state = "EXECUTING"
                self._operation = f"执行步骤 {idx}/{total}: {step_id}"
                self._active_tasks = 1 if self._busy else 0
                self._refresh_header_panel()
                self._refresh_status()
                return

            if et == "user_message":
                txt = str(data.get("text", "")).strip()
                if txt:
                    t = Text()
                    t.append("you: ", style="bold blue")
                    t.append(txt)
                    conversation.write(t)
                    if self._follow:
                        conversation.scroll_end(animate=False)
                return

            if et in {"assistant_text", "assistant"}:
                txt = str(data.get("text", "")).strip()
                if txt:
                    t = Text()
                    t.append("assistant: ", style="bold magenta")
                    t.append(txt)
                    conversation.write(t)
                    if self._follow:
                        conversation.scroll_end(animate=False)
                # 对齐 enhanced：assistant_text 视为本轮已结束
                self._state = "DONE"
                self._operation = "本轮结束"
                self._active_tasks = 0
                self._refresh_header_panel()
                self._refresh_status()
                self._refresh_ops()
                return

            if et == "display":
                content = str(data.get("content", "")).strip()
                if content:
                    t = Text()
                    t.append("agent: ", style="cyan")
                    t.append(content)
                    conversation.write(t)
                    if self._follow:
                        conversation.scroll_end(animate=False)
                return

            if et == "llm_request":
                self._state = "EXECUTING"
                self._operation = "LLM 请求"
                mc = data.get("messages")
                if isinstance(mc, int) and mc >= 0:
                    self._last_llm_messages = mc
                self._active_tasks = 1
                self._refresh_header_panel()
                self._refresh_status()
                self._refresh_ops()
                return

            if et == "llm_request_params":
                pt = data.get("prompt_tokens_est")
                if isinstance(pt, int) and pt >= 0:
                    self._llm_prompt = pt
                mc = data.get("messages_count")
                if isinstance(mc, int) and mc >= 0:
                    self._last_llm_messages = mc
                self._state = "EXECUTING"
                self._operation = "LLM 请求"
                self._active_tasks = 1
                self._refresh_header_panel()
                self._refresh_status()
                self._refresh_ops()
                return

            if et == "llm_usage":
                pt = data.get("prompt_tokens_est")
                if isinstance(pt, int) and pt >= 0:
                    self._llm_prompt = pt
                ct = data.get("completion_tokens_est")
                if isinstance(ct, int) and ct >= 0:
                    self._llm_completion = ct
                elapsed_ms = data.get("elapsed_ms") or 0
                self._tps = (self._llm_completion / elapsed_ms) * 1000 if elapsed_ms else 0.0
                self._state = "EXECUTING"
                self._operation = "LLM 返回"
                self._active_tasks = 0
                self._recent_completed.append("LLM")
                self._refresh_header_panel()
                self._refresh_status()
                return

            if et == "tool_call_parsed":
                tool = str(data.get("tool", ""))
                args_str = str(data.get("args", {}) or {})
                if len(args_str) > 180:
                    args_str = args_str[:179] + "…"
                self._last_tool = tool
                self._last_tool_args = args_str
                self._state = "EXECUTING"
                self._operation = f"工具: {tool}"
                self._active_tasks = 1
                self._refresh_header_panel()
                self._refresh_status()
                self._refresh_ops()
                return

            if et == "tool_result":
                tool = str(data.get("tool", ""))
                ok = bool(data.get("ok"))
                err = str(data.get("error") or "")
                if len(err) > 160:
                    err = err[:159] + "…"
                icon = "✓ " if ok else "✗ "
                icon_style = "green" if ok else "red"
                tr = Text()
                tr.append(icon, style=icon_style)
                tr.append(tool)
                if err:
                    tr.append("  ")
                    tr.append(err, style="dim")
                self._last_tool_result = tr
                self._state = "EXECUTING"
                self._operation = f"工具完成: {tool}"
                self._active_tasks = 0
                self._recent_completed.append(f"{'✓' if ok else '✗'} {tool}")
                self._refresh_header_panel()
                self._refresh_status()
                self._refresh_ops()
                return

        def _drain_events(self) -> None:
            drained = 0
            while drained < 200:
                try:
                    ev = q.get_nowait()
                except Empty:
                    break
                self._apply_event(ev)
                drained += 1

        def on_input_submitted(self, event: Input.Submitted) -> None:
            txt = (event.value or "").strip()
            self.query_one("#input", Input).value = ""
            if not txt:
                return
            if self._busy:
                self.query_one("#events", _Log).write("[yellow]当前正在执行上一条请求，请稍候…[/yellow]")
                return
            if txt.lower() in {"exit", "quit", "/exit", "/quit"}:
                self.exit()
                return

            # 先写入本地对话框（与 AgentLoop 的 user_message 事件保持一致）
            try:
                q.put_nowait({"event": "user_message", "data": {"text": txt}})
            except Exception:
                pass

            self._busy = True

            def _worker() -> None:
                def _confirm(_msg: str) -> bool:
                    # 说明：TUI 版暂未实现交互确认（Modal），先默认拒绝，避免卡住终端输入。
                    try:
                        q.put_nowait(
                            {
                                "event": "display",
                                "data": {
                                    "content": "TUI(opencode) 模式暂不支持交互确认(confirm)。如需写文件/执行命令，请用 classic/enhanced，或临时关闭 confirm_write/confirm_exec。",
                                    "level": "warning",
                                },
                            }
                        )
                    except Exception:
                        pass
                    return False

                def _on_event(e: dict[str, Any]) -> None:
                    try:
                        q.put_nowait({"event": e.get("event"), "data": e.get("data", {}) or {}, "step": e.get("step")})
                    except Exception:
                        pass

                try:
                    run_turn(txt, _confirm, _on_event)
                finally:
                    self._busy = False

            Thread(target=_worker, daemon=True).start()

    OpencodeTUI().run()



