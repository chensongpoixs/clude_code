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
import time
from rich.text import Text
from rich.table import Table
from rich.syntax import Syntax
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
            self._verbosity: str = "compact"  # compact|verbose|debug（仅影响“对话/输出”的块内容）

        def _now_hhmmss(self) -> str:
            try:
                return time.strftime("%H:%M:%S", time.localtime())
            except Exception:
                return ""

        def _short_trace(self, trace_id: str | None) -> str:
            t = (trace_id or "").strip()
            return t[:8] if t else "-"

        def _level_style(self, level: str) -> str:
            lv = (level or "").strip().lower()
            return {
                "info": "cyan",
                "progress": "blue",
                "warning": "yellow",
                "warn": "yellow",
                "error": "red",
                "success": "green",
            }.get(lv, "cyan")

        def _push_structured_block(
            self,
            *,
            title: str,
            level: str = "info",
            step: int | str | None = None,
            ev: str | None = None,
            trace_id: str | None = None,
            summary: str | None = None,
            decision: str | None = None,
            evidence: list[str] | None = None,
            hint: str | None = None,
            force_show_decision: bool = False,
        ) -> None:
            """
            在“对话/输出”窗格输出结构化块：
            - 头部：time/LEVEL/step/ev/trace
            - 正文：Summary / Why / Evidence（摘要优先）
            """
            conversation = self.query_one("#conversation", _Log)
            ttl = (title or "").strip()
            if not ttl:
                return
            lv = (level or "info").strip().upper()
            t = self._now_hhmmss()
            st = "-" if step is None else str(step)
            et = (ev or "").strip() or "-"
            tr = self._short_trace(trace_id)
            head = f"[{t}] [{lv}] step={st} ev={et} trace={tr}  {ttl}".strip()

            color = self._level_style(level)
            conversation.write(Text(f"┌─ {head}", style=color))

            def _w(prefix: str, txt: str | None) -> None:
                s = (txt or "").strip()
                if not s:
                    return
                # 防止爆屏：对话区每行尽量短一些
                if len(s) > 500 and self._verbosity != "debug":
                    s = s[:499] + "…"
                conversation.write(Text(f"│ {prefix}{s}", style=color))

            _w("Summary: ", summary)
            if force_show_decision or self._verbosity in {"verbose", "debug"}:
                _w("Why: ", decision)
            if evidence:
                if self._verbosity == "compact":
                    ev_lines = evidence[:6]
                else:
                    ev_lines = evidence[:12]
                for ln in ev_lines:
                    ln = (ln or "").strip()
                    if not ln:
                        continue
                    if len(ln) > 520 and self._verbosity != "debug":
                        ln = ln[:519] + "…"
                    conversation.write(Text(f"│ Evidence: {ln}", style=color))
                if len(evidence) > len(ev_lines):
                    conversation.write(Text("│ Evidence: …(更多证据见“事件/操作面板”)", style=color))
            if hint:
                _w("Hint: ", hint)
            conversation.write(Text("└─", style=color))
            if self._follow:
                try:
                    conversation.scroll_end(animate=False)
                except Exception:
                    pass

        def _summarize_tool_args(self, tool: str, args: dict[str, Any]) -> list[str]:
            """从 args 中提炼“对话区可读证据”，避免 dump 全量 JSON。"""
            tool = (tool or "").strip()
            args = args or {}
            evs: list[str] = []
            if tool == "read_file":
                evs.append(f"path={args.get('target_file')}")
                if args.get("offset") is not None:
                    evs.append(f"offset={args.get('offset')}")
                if args.get("limit") is not None:
                    evs.append(f"limit={args.get('limit')}")
            elif tool == "grep":
                evs.append(f"pattern={args.get('pattern')}")
                if args.get("path"):
                    evs.append(f"path={args.get('path')}")
                if args.get("glob"):
                    evs.append(f"glob={args.get('glob')}")
            elif tool == "apply_patch":
                # patch 内容可能很长：只提示“已提交 patch”，详情看事件窗格
                evs.append("patch=*** Begin Patch …")
            elif tool in {"run_terminal_cmd", "run_cmd"}:
                cmd = args.get("command") or args.get("cmd")
                evs.append(f"command={cmd}")
                if args.get("is_background") is not None:
                    evs.append(f"is_background={args.get('is_background')}")
            elif tool in {"web_search", "webfetch"}:
                q = args.get("search_term") or args.get("url")
                evs.append(f"q={q}")
            else:
                # 默认提炼少量关键字段
                for k in ("target_file", "target_directory", "glob_pattern", "query", "explanation", "name"):
                    if k in args and args.get(k) is not None:
                        evs.append(f"{k}={args.get(k)}")
            return [str(x) for x in evs if x not in ("None", "")]

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
            # 结构化：LLM + Tool 快照（便于排查）
            llm_t = Table(show_header=False, box=None, pad_edge=False)
            llm_t.add_column(justify="left", style="bold", width=8)
            llm_t.add_column(justify="left")
            if self._last_llm_messages is not None:
                llm_t.add_row("LLM", f"messages={self._last_llm_messages}")
            llm_t.add_row("用量", self._render_top_metrics())
            ops.write(llm_t)

            ops.write(Text(""))
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

        def _append_event_line(self, et: str, data: dict[str, Any], *, step: int | str | None = None) -> None:
            events = self.query_one("#events", _Log)

            # 事件摘要行（一眼能看懂 + 可定位）
            head = Text()
            head.append(f"{step} " if step is not None else "", style="dim")
            head.append(et, style="bold")

            # 简短摘要字段（对调试最有价值）
            summary = ""
            if et == "state":
                summary = f"state={data.get('state')}"
            elif et == "plan_step_start":
                summary = f"{data.get('idx')}/{data.get('total')} step_id={data.get('step_id')}"
            elif et == "llm_request_params":
                summary = f"model={data.get('model')} api={data.get('api_mode')} messages={data.get('messages_count')}"
            elif et == "llm_usage":
                summary = f"prompt={data.get('prompt_tokens_est')} output={data.get('completion_tokens_est')} elapsed_ms={data.get('elapsed_ms')}"
            elif et == "tool_call_parsed":
                summary = f"tool={data.get('tool')}"
            elif et == "tool_result":
                summary = f"tool={data.get('tool')} ok={data.get('ok')}"

            if summary:
                head.append(" ", style="dim")
                head.append(summary, style="dim")
            events.write(head)

            # 关键事件：输出格式化 JSON（可滚轮查看完整细节）
            if et in {"llm_request_params", "llm_usage", "tool_call_parsed", "tool_result", "plan_generated", "replan_generated", "plan_parse_failed"}:
                try:
                    s = json.dumps(data, ensure_ascii=False, default=str, indent=2)
                except Exception:
                    s = str(data)
                if len(s) > 8000:
                    s = s[:7999] + "…"
                events.write(Syntax(s, "json", word_wrap=True, line_numbers=False))

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
            trace_id = ev.get("trace_id")

            conversation = self.query_one("#conversation", _Log)
            status = self.query_one("#status", _Log)
            ops = self.query_one("#ops", _Log)

            self._append_event_line(et, data, step=ev.get("step"))

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
                # 对话区：给一条“过程解释”块（更像 Claude Code 的可读叙事）
                self._push_structured_block(
                    title="状态切换",
                    level="progress" if self._state in {"PLANNING", "EXECUTING"} else "info",
                    step=ev.get("step"),
                    ev=et,
                    trace_id=trace_id,
                    summary=f"state={self._state}",
                    decision=str(data.get("reason") or data.get("step") or data.get("mode") or ""),
                )
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
                self._push_structured_block(
                    title="执行步骤开始",
                    level="progress",
                    step=ev.get("step"),
                    ev=et,
                    trace_id=trace_id,
                    summary=f"{idx}/{total}  step_id={step_id}",
                    decision="开始执行本步骤；后续将根据模型输出调用工具并回喂结果。",
                    evidence=[f"step_id={step_id}"],
                )
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

            if et in {"intent_classified"}:
                cat = data.get("category")
                conf = data.get("confidence")
                self._push_structured_block(
                    title="意图识别",
                    level="info",
                    step=ev.get("step"),
                    ev=et,
                    trace_id=trace_id,
                    summary=f"category={cat} confidence={conf}",
                    decision="用于决定是否进入 planning 阶段，以及工具/验证策略的优先级。",
                )
                return

            if et in {"planning_llm_request"}:
                self._state = "PLANNING"
                self._operation = "规划：LLM 请求"
                self._active_tasks = 1
                self._refresh_header_panel()
                self._refresh_status()
                self._push_structured_block(
                    title="进入规划阶段（生成 Plan）",
                    level="progress",
                    step=ev.get("step"),
                    ev=et,
                    trace_id=trace_id,
                    summary=f"attempt={data.get('attempt')}",
                    decision="将任务拆成可执行步骤，降低一次性长上下文失败概率，并提高可追溯性。",
                )
                return

            if et in {"plan_generated"}:
                title = str(data.get("title") or "").strip()
                steps = data.get("steps")
                preview = data.get("steps_preview") or []
                evs: list[str] = []
                if isinstance(preview, list):
                    for p in preview[:8]:
                        evs.append(str(p))
                self._push_structured_block(
                    title="计划已生成（Plan）",
                    level="success",
                    step=ev.get("step"),
                    ev=et,
                    trace_id=trace_id,
                    summary=f"title={title} steps={steps}",
                    decision="接下来会按步骤执行：每步会触发 LLM→工具→回喂→（可选）验证的闭环。",
                    evidence=evs,
                    hint="更多结构化细节见“事件”窗格（plan_generated JSON）。",
                )
                return

            if et in {"plan_parse_failed"}:
                self._push_structured_block(
                    title="计划解析失败",
                    level="error",
                    step=ev.get("step"),
                    ev=et,
                    trace_id=trace_id,
                    summary=f"attempt={data.get('attempt')} error={data.get('error')}",
                    decision="将要求模型仅输出严格 JSON，触发重试（或降级到 ReAct）。",
                    hint="建议缩小任务、提高结构化约束，或指定入口文件。",
                )
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
                level = str(data.get("level") or "info")
                title = str(data.get("title") or "Agent 输出").strip()
                thought = str(data.get("thought") or "").strip()
                explanation = str(data.get("explanation") or "").strip()
                ev_lines = data.get("evidence")
                evidence: list[str] | None = None
                if isinstance(ev_lines, list):
                    evidence = [str(x) for x in ev_lines if str(x).strip()]
                if content:
                    self._push_structured_block(
                        title=title,
                        level=level,
                        step=ev.get("step"),
                        ev=et,
                        trace_id=trace_id,
                        summary=content,
                        decision=(thought or explanation),
                        evidence=evidence,
                        hint="（display 工具输出）",
                        # display 的核心价值就是“过程可见”，因此强制显示 Why（思考过程）
                        force_show_decision=True,
                    )
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
                conversation.write(Text("🤖 LLM 请求中...", style="dim"))
                if self._follow:
                    conversation.scroll_end(animate=False)
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
                self._push_structured_block(
                    title="LLM 请求参数",
                    level="info",
                    step=ev.get("step"),
                    ev=et,
                    trace_id=trace_id,
                    summary=f"model={data.get('model')} api={data.get('api_mode')} base_url={data.get('base_url')}",
                    decision=f"temperature={data.get('temperature')} max_tokens={data.get('max_tokens')}",
                    evidence=[
                        f"prompt_tokens_est={data.get('prompt_tokens_est')}",
                        f"messages_count={data.get('messages_count')}",
                    ],
                    hint="完整参数见“事件”窗格（llm_request_params JSON）。",
                )
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
                self._refresh_ops()
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
                args = data.get("args", {}) or {}
                evs = self._summarize_tool_args(tool, args if isinstance(args, dict) else {})
                self._push_structured_block(
                    title=f"工具调用: {tool}",
                    level="progress",
                    step=ev.get("step"),
                    ev=et,
                    trace_id=trace_id,
                    summary="模型已解析出工具调用，将进行策略校验并执行工具。",
                    decision="对话区仅展示关键参数摘要；详情见“事件/操作面板”。",
                    evidence=evs or [f"args={args_str}"],
                )
                return

            if et == "tool_result":
                tool = str(data.get("tool", ""))
                ok = bool(data.get("ok"))
                err_obj = data.get("error")
                err = str(err_obj or "")
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
                level = "success" if ok else "error"
                code = ""
                if isinstance(err_obj, dict):
                    code = str(err_obj.get("code") or "")
                self._push_structured_block(
                    title=f"工具结果: {tool}",
                    level=level,
                    step=ev.get("step"),
                    ev=et,
                    trace_id=trace_id,
                    summary=f"ok={ok}" + (f" code={code}" if code else "") + (f" err={err}" if err and not ok else ""),
                    decision="工具结果已回喂给模型（作为后续推理依据）。",
                    hint="更完整的 payload/原始错误见“事件/操作面板”。",
                )
                return

            if et in {"policy_deny_tool", "policy_deny_cmd", "denied_by_user"}:
                self._push_structured_block(
                    title="策略/确认拦截",
                    level="error",
                    step=ev.get("step"),
                    ev=et,
                    trace_id=trace_id,
                    summary=str(data),
                    decision="为避免危险操作，本次调用被策略或用户确认拒绝。",
                    hint="如需继续：调整 allowed_tools/disallowed_tools 或关闭 confirm_write/confirm_exec（不推荐在不可信项目中关闭）。",
                )
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



