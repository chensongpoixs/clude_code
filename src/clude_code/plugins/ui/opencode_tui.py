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
import threading
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
    _confirm_lock = threading.Lock()
    _confirm_seq = 0
    _confirm_waiters: dict[int, dict[str, Any]] = {}

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
        /* 主区（对话/输出 + 操作面板）与事件区尽量等高，便于排查问题 */
        #main { height: 1fr; min-height: 10; }
        /* 顶部 clude chat 面板：按内容自适应，避免多余空白 */
        #header_panel { height: auto; min-height: 3; }
        #left { width: 3fr; }
        #right { width: 2fr; }
        /* 输入框：需要给边框/提示留空间，否则会导致无法输入或不可见 */
        #input_row { height: 3; min-height: 3; }
        /* 事件区：提高高度（与主区接近等高）；并给最小高度避免太扁 */
        #events { height: 1fr; min-height: 10; }
        _Log { border: solid $primary; }
        /* 所有小窗口标题居中（对齐你的要求） */
        #header_panel, #conversation, #ops, #events, #input { border-title-align: center; }
        /* 右侧：操作面板吃掉剩余高度 */
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
            # 对话窗格风格：log = 复刻 chat 默认“执行日志流”；block = 结构化块
            self._conversation_mode: str = "log"
            self._llm_round: int = 0

            # 交互确认（confirm）状态
            self._pending_confirm_id: int | None = None
            self._pending_confirm_msg: str | None = None
            self._input_placeholder_normal: str = "输入内容，回车发送（q 退出）"

            # LLM 请求历史（用于“操作面板”的多条进度条展示）
            # 每条：{id, idx, kind, step_id, start_ts, elapsed_ms, status, model, prompt_tokens, completion_tokens}
            self._llm_req_seq: int = 0
            self._llm_requests: deque[dict[str, Any]] = deque(maxlen=12)
            self._active_llm_id: int | None = None
            self._spinner_frames: tuple[str, ...] = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")
            self._spinner_idx: int = 0

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

        def _event_phase(self) -> str:
            """把内部状态映射到更稳定的 phase 展示字段（用于事件窗格摘要）。"""
            st = (self._state or "").strip().upper()
            if st in {"INTAKE", "PLANNING", "EXECUTING", "VERIFY", "DONE"}:
                return st
            if st in {"IDLE"}:
                return "IDLE"
            return st or "UNK"

        def _event_level_code(self, et: str, data: dict[str, Any]) -> str:
            """
            事件级别（用于事件窗格摘要）：
            - E: Error
            - W: Warning
            - I: Info
            - D: Debug
            """
            et = (et or "").strip()
            if et in {"plan_parse_failed", "policy_deny_tool", "policy_deny_cmd", "denied_by_user"}:
                return "E"
            if et in {"stuttering_detected"}:
                return "W"
            if et == "tool_result":
                ok = bool((data or {}).get("ok"))
                return "I" if ok else "E"
            if et in {"llm_request_params", "llm_usage"}:
                return "D"
            return "I"

        def _event_summary(self, et: str, data: dict[str, Any]) -> str:
            """把不同事件压缩成一段“人能扫读”的摘要（一级节点用）。"""
            data = data or {}
            if et == "state":
                return f"state={data.get('state')} reason={data.get('reason') or data.get('step') or data.get('mode')}"
            if et == "intent_classified":
                return f"category={data.get('category')} conf={data.get('confidence')}"
            if et == "planning_llm_request":
                return f"attempt={data.get('attempt')}"
            if et == "plan_generated":
                return f"title={data.get('title')} steps={data.get('steps')}"
            if et == "plan_step_start":
                return f"{data.get('idx')}/{data.get('total')} step_id={data.get('step_id')}"
            if et == "llm_request_params":
                return (
                    f"model={data.get('model')} prompt={data.get('prompt_tokens_est')} "
                    f"max={data.get('max_tokens')} temp={data.get('temperature')}"
                )
            if et == "llm_usage":
                return (
                    f"prompt={data.get('prompt_tokens_est')} completion={data.get('completion_tokens_est')} "
                    f"elapsed_ms={data.get('elapsed_ms')}"
                )
            if et == "tool_call_parsed":
                tool = str(data.get("tool") or "")
                args = data.get("args") or {}
                evs = self._summarize_tool_args(tool, args if isinstance(args, dict) else {})
                evs_s = " ".join(evs[:3]) if evs else ""
                return f"tool={tool}" + (f" {evs_s}" if evs_s else "")
            if et == "tool_result":
                tool = str(data.get("tool") or "")
                ok = bool(data.get("ok"))
                err = data.get("error")
                code = ""
                msg = ""
                if isinstance(err, dict):
                    code = str(err.get("code") or "")
                    msg = str(err.get("message") or "")
                else:
                    msg = str(err or "")
                if msg and len(msg) > 80:
                    msg = msg[:79] + "…"
                return f"tool={tool} ok={ok}" + (f" code={code}" if code else "") + (f" err={msg}" if msg and not ok else "")
            if et == "display":
                title = str(data.get("title") or "display")
                content = str(data.get("content") or "")
                content = content.strip().replace("\n", " ")
                if len(content) > 80:
                    content = content[:79] + "…"
                return f"title={title} {content}".strip()
            if et in {"policy_deny_tool"}:
                return f"tool={data.get('tool')} reason={data.get('reason')}"
            if et in {"policy_deny_cmd"}:
                c = str(data.get("command") or "")
                c = c.replace("\n", " ")
                if len(c) > 80:
                    c = c[:79] + "…"
                return f"cmd={c} reason={data.get('reason')}"
            if et == "denied_by_user":
                return f"tool={data.get('tool')}"
            return ""

        def _event_icon(self, lvl: str, et: str, data: dict[str, Any]) -> tuple[str, str]:
            """事件摘要行的小图标（更好扫读）。返回 (icon, style)。"""
            if et == "tool_result":
                ok = bool((data or {}).get("ok"))
                return ("✓" if ok else "✗", "bold green" if ok else "bold red")
            if lvl == "E":
                return ("✗", "bold red")
            if lvl == "W":
                return ("⚠", "bold yellow")
            if lvl == "D":
                return ("·", "dim")
            return ("•", "bold white")

        def _event_name_style(self, et: str) -> str:
            et = (et or "").strip()
            if et.startswith("llm_"):
                return "bold magenta"
            if et.startswith("tool_"):
                return "bold yellow"
            if et.startswith("plan_") or et.startswith("planning_"):
                return "bold cyan"
            if et.startswith("policy_") or et in {"denied_by_user"}:
                return "bold red"
            if et == "state":
                return "bold blue"
            if et == "display":
                return "bold cyan"
            return "bold"

        def _one_line(self, s: Any, limit: int = 140) -> str:
            try:
                t = str(s or "").replace("\n", " ").strip()
            except Exception:
                return ""
            if len(t) > limit:
                t = t[: limit - 1] + "…"
            return t

        def _fmt_duration(self, seconds: float) -> str:
            try:
                s = max(0, int(seconds))
                m, s = divmod(s, 60)
                h, m = divmod(m, 60)
                if h > 0:
                    return f"{h}:{m:02d}:{s:02d}"
                return f"0:{m:02d}:{s:02d}"
            except Exception:
                return "0:00:00"

        def _format_llm_progress_line(self, *, idx: int, purpose: str, done: bool, elapsed_s: float) -> Text:
            """
            控制面板里的 LLM 请求进度行，形态对齐你给的参考：
            1. LLM 请求 [目的]   0% -:--:--
            """
            mid = (purpose or "分析").strip()
            if len(mid) > 24:
                mid = mid[:23] + "…"
            # 样式对齐：LLM 请求 [xxxxxxx]   0% -:--:--
            mid = f"[{mid}]"
            pct = "100%" if done else "0%"
            tail = self._fmt_duration(elapsed_s) if done else "-:--:--"
            spin = "" if done else (self._spinner_frames[self._spinner_idx % len(self._spinner_frames)] + " ")

            t = Text()
            t.append(f"{idx}. ", style="dim")
            t.append(spin, style="yellow" if not done else "dim")
            t.append("LLM 请求 ", style="bold")
            t.append(mid, style="bold cyan" if done else "bold yellow")
            t.append("   ", style="dim")
            t.append(f"{pct} ", style="bold green" if done else "yellow")
            t.append(tail, style="white" if done else "dim")
            return t

        def _llm_start(self, *, kind: str, step_id: str | None = None, purpose: str | None = None) -> None:
            self._llm_req_seq += 1
            p = (purpose or "").strip()
            if not p:
                # 先给一个占位目的；更准确的目的会在 llm_request_params 里根据 stage/step_id 自动修正
                p = "准备请求"
            rec: dict[str, Any] = {
                "id": self._llm_req_seq,
                "idx": self._llm_req_seq,
                "kind": kind,  # planning|execute_step|react|unknown
                "step_id": step_id,
                "purpose": p,
                "start_ts": time.time(),
                "elapsed_ms": None,
                "status": "running",
                "model": None,
                "prompt_tokens": None,
                "completion_tokens": None,
            }
            self._llm_requests.append(rec)
            self._active_llm_id = rec["id"]

        def _llm_attach_params(self, data: dict[str, Any]) -> None:
            if self._active_llm_id is None:
                return
            try:
                rec = next((r for r in reversed(self._llm_requests) if r.get("id") == self._active_llm_id), None)
                if not rec:
                    return
                # 用 stage/step_id 推导“本次请求目的”（这比仅靠 kind/step_id 更准确）
                stage = str(data.get("stage") or "").strip()
                sid = str(data.get("step_id") or "").strip() or None
                if stage:
                    rec["kind"] = stage
                    rec["step_id"] = sid
                    if stage == "planning":
                        rec["purpose"] = "生成整体计划"
                    elif stage == "replan":
                        rec["purpose"] = f"重规划 {sid}" if sid else "重规划步骤"
                    elif stage == "execute_step":
                        # execute_step 的核心目标：分析当前步骤并决定下一动作（工具/完成/重规划）
                        rec["purpose"] = f"分析步骤 {sid}" if sid else "分析并决定下一步"
                    elif stage == "react_fallback":
                        rec["purpose"] = "ReAct 决策/直接回答"
                    else:
                        # 其它阶段：给一个可读兜底
                        rec["purpose"] = stage
                if data.get("model"):
                    rec["model"] = data.get("model")
                if isinstance(data.get("prompt_tokens_est"), int):
                    rec["prompt_tokens"] = data.get("prompt_tokens_est")
            except Exception:
                pass

        def _llm_finish(self, data: dict[str, Any]) -> None:
            if self._active_llm_id is None:
                return
            try:
                rec = next((r for r in reversed(self._llm_requests) if r.get("id") == self._active_llm_id), None)
                if not rec:
                    return
                elapsed_ms = data.get("elapsed_ms")
                if isinstance(elapsed_ms, int) and elapsed_ms >= 0:
                    rec["elapsed_ms"] = elapsed_ms
                if isinstance(data.get("completion_tokens_est"), int):
                    rec["completion_tokens"] = data.get("completion_tokens_est")
                rec["status"] = "done"
            finally:
                self._active_llm_id = None

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

        def _push_chat_log(self, text: str, *, style: str = "white") -> None:
            """在对话窗格输出“chat 默认日志流”的一行。"""
            t = (text or "").rstrip()
            if not t:
                return
            conv = self.query_one("#conversation", _Log)
            conv.write(Text(t, style=style))
            if self._follow:
                try:
                    conv.scroll_end(animate=False)
                except Exception:
                    pass

        def _format_args_one_line(self, args: Any, *, limit: int = 220) -> str:
            try:
                s = json.dumps(args, ensure_ascii=False, default=str)
            except Exception:
                s = str(args)
            s = s.replace("\n", " ").strip()
            if len(s) > limit:
                s = s[: limit - 1] + "…"
            return s

        def _format_tool_result_summary(self, tool: str, ok: bool, data: dict[str, Any]) -> str:
            """尽量用人能理解的方式概括 tool_result。"""
            err = data.get("error")
            if not ok:
                if isinstance(err, dict):
                    code = err.get("code")
                    msg = err.get("message")
                    return f"失败: {code} {self._one_line(msg, 140)}".strip()
                return f"失败: {self._one_line(err, 140)}".strip()
            payload = data.get("payload") or {}
            if tool == "list_dir" and isinstance(payload, dict):
                # 兼容不同实现：items/entries 可能存在
                items = payload.get("items") or payload.get("entries")
                if isinstance(items, list):
                    return f"成功: {len(items)} 项"
            if tool == "grep" and isinstance(payload, dict):
                hits = payload.get("hits") or payload.get("matches") or payload.get("count")
                if isinstance(hits, int):
                    return f"成功: 找到 {hits} 个匹配"
            if tool == "read_file" and isinstance(payload, dict):
                content = payload.get("content") or payload.get("text")
                if isinstance(content, str):
                    return f"成功: 读取 {len(content)} 字符"
            return "成功"

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
                    yield _Log(id="ops")
            with Horizontal(id="input_row"):
                yield Input(placeholder=self._input_placeholder_normal, id="input")
            # 事件窗格：纯日志输出（不支持折叠/展开，便于“顺序回放 + 复制粘贴”排障）
            yield _Log(id="events")
            yield Footer()

        def on_mount(self) -> None:
            # 为每个“窗口”设置边框标题（对齐 enhanced 的分区命名）
            header_panel = self.query_one("#header_panel", _Log)
            conversation = self.query_one("#conversation", _Log)
            ops_panel = self.query_one("#ops", _Log)
            events_panel = self.query_one("#events", _Log)
            input_box = self.query_one("#input", Input)

            header_panel.border_title = "clude chat"
            conversation.border_title = "对话/输出"
            ops_panel.border_title = "操作面板"
            events_panel.border_title = "事件"
            input_box.border_title = "you"

            # 标题居中（Textual 支持 border_title_align）
            for w in (header_panel, conversation, ops_panel, events_panel, input_box):
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
            self._refresh_ops()

            self.query_one("#events", _Log).write(
                Text("提示：事件窗格为顺序日志（不支持折叠/展开）；关键事件会输出摘要 + JSON。", style="dim")
            )
            self.set_interval(0.05, self._drain_events)
            # 仅用于“正在请求中”的 spinner 动画：轻量刷新 ops
            self.set_interval(0.15, self._tick_ops_spinner)

        def _tick_ops_spinner(self) -> None:
            """请求进行中时刷新 spinner（不依赖新事件到来）。"""
            if self._active_llm_id is None and not self._busy:
                return
            self._spinner_idx = (self._spinner_idx + 1) % 10_000
            try:
                self._refresh_ops()
            except Exception:
                pass

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

            # 第三行：把原“状态”窗格信息合并进来（模型/地址/任务）
            row3 = Table.grid(expand=True)
            row3.add_column(justify="left", ratio=3, no_wrap=True)
            row3.add_column(justify="left", ratio=5, no_wrap=True)
            row3.add_column(justify="right", ratio=4, no_wrap=True)
            model = (self._model or "auto")[:48]
            base = (self._base_url or "")[:80]
            t_model = Text(f"模型: {model}", style="dim")
            t_base = Text(f"地址: {base}" if base else "地址: -", style="dim")
            t_tasks = Text(f"任务: {self._active_tasks} 活跃 / {len(self._recent_completed)} 最近完成", style="dim")
            row3.add_row(t_model, t_base, t_tasks)
            hp.write(row3)

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
            ops.write(llm_t)

            ops.write(Text(""))

            # LLM 请求历史（多条）
            if self._llm_requests:
                ops.write(Text("LLM 请求", style="bold dim"))
                for r in list(self._llm_requests)[-6:]:
                    done = (r.get("status") == "done")
                    start_ts = float(r.get("start_ts") or time.time())
                    if done and isinstance(r.get("elapsed_ms"), int):
                        elapsed_s = float(r["elapsed_ms"]) / 1000.0
                    else:
                        elapsed_s = time.time() - start_ts
                    purpose = str(r.get("purpose") or "") or str(r.get("kind") or "分析")
                    ops.write(
                        self._format_llm_progress_line(
                            idx=int(r.get("idx") or 0),
                            purpose=purpose,
                            done=done,
                            elapsed_s=elapsed_s,
                        )
                    )
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
            # RichLog panes 支持 auto_scroll
            for wid in ("#conversation", "#ops", "#events"):
                try:
                    self.query_one(wid, _Log).auto_scroll = self._follow
                except Exception:
                    pass

        def action_toggle_follow(self) -> None:
            self._set_follow(not self._follow)
            try:
                self.query_one("#events", _Log).write(Text(f"follow={'on' if self._follow else 'off'}", style="dim"))
            except Exception:
                pass

        def action_jump_bottom(self) -> None:
            # 回到底部并开启 follow
            self._set_follow(True)
            for wid in ("#conversation", "#ops", "#events"):
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

        def _append_event_line(
            self,
            et: str,
            data: dict[str, Any],
            *,
            step: int | str | None = None,
            trace_id: str | None = None,
        ) -> None:
            """
            事件窗格（日志）：
            - 每条事件输出一行强摘要（可扫读）
            - 关键事件输出格式化 JSON（可复制粘贴排障）
            """
            events = self.query_one("#events", _Log)

            ts = self._now_hhmmss()
            st = "-" if step is None else str(step)
            tr = (trace_id or "").strip()
            tr8 = tr[:8] if tr else "-"
            phase = self._event_phase()
            lvl = self._event_level_code(et, data)
            icon, icon_style = self._event_icon(lvl, et, data)
            summary = self._one_line(self._event_summary(et, data), 150)

            label_text = Text()
            label_text.append(f"[{ts}] ", style="dim")
            label_text.append(f"{icon} ", style=icon_style)
            label_text.append(f"{phase} ", style="dim")
            label_text.append(f"step={st} ", style="dim")
            label_text.append(et, style=self._event_name_style(et))
            label_text.append("  ", style="dim")
            label_text.append(f"trace={tr8}", style="dim cyan")
            if summary:
                label_text.append("  |  ", style="dim")
                label_text.append(summary, style="white" if lvl != "D" else "dim")

            events.write(label_text)

            # 输出 JSON（只对关键事件，避免刷屏）
            if et in {
                "llm_request_params",
                "llm_usage",
                "tool_call_parsed",
                "tool_result",
                "plan_generated",
                "replan_generated",
                "plan_parse_failed",
                "policy_deny_tool",
                "policy_deny_cmd",
            }:
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
            ops = self.query_one("#ops", _Log)

            self._append_event_line(et, data, step=ev.get("step"), trace_id=trace_id)

            # --- 对话/输出：chat 默认日志流（你要求的格式） ---
            if self._conversation_mode == "log":
                if et == "turn_start":
                    self._llm_round = 0
                    self._push_chat_log(f"开始新的一轮对话 trace_id={trace_id}", style="bold cyan")
                elif et == "user_message":
                    self._push_chat_log(f"用户输入: {data.get('text')}", style="white")
                elif et == "intent_classified":
                    cat = data.get("category")
                    conf = data.get("confidence")
                    # category 可能是 {value: "..."} 或字符串
                    if isinstance(cat, dict) and "value" in cat:
                        cat = cat.get("value")
                    self._push_chat_log(f"意图识别结果: {cat} (置信度: {conf})", style="dim")
                elif et == "planning_skipped":
                    self._push_chat_log("检测到能力询问或通用对话，跳过显式规划阶段。", style="dim")
                elif et == "user_content_built":
                    prev = str(data.get("preview") or "")
                    trunc = bool(data.get("truncated"))
                    if trunc:
                        prev = prev + "…"
                    self._push_chat_log(f"user input LLM  user_content={prev}", style="dim")
                elif et == "llm_request_params":
                    # 以 params 事件作为“本轮请求”计数入口（包含 stage/messages）
                    self._llm_round += 1
                    mc = data.get("messages_count")
                    self._push_chat_log(f"→ 第 {self._llm_round} 轮：请求 LLM（消息数={mc}）", style="bold")
                    self._push_chat_log(
                        f"LLM 请求参数: model={data.get('model')} api_mode={data.get('api_mode')} messages={data.get('messages_count')}",
                        style="dim",
                    )
                elif et == "llm_response_data":
                    self._push_chat_log(f"LLM 返回摘要: text_length={data.get('text_length')}", style="dim")
                elif et == "tool_call_parsed":
                    tool = str(data.get("tool") or "")
                    args = data.get("args") or {}
                    self._push_chat_log(
                        f"🔧 解析到工具调用: {tool} [轮次] {self._llm_round} [参数] {self._format_args_one_line(args)}",
                        style="yellow",
                    )
                    self._push_chat_log(f"▶ 执行工具: {tool}", style="yellow")
                elif et == "display":
                    # display 属于 Agent 主动输出
                    content = str(data.get("content") or "").strip()
                    if content:
                        self._push_chat_log(f"ℹ️ {self._one_line(content, 240)}", style="cyan")
                elif et == "tool_result":
                    tool = str(data.get("tool") or "")
                    ok = bool(data.get("ok"))
                    icon = "✓" if ok else "✗"
                    style = "green" if ok else "red"
                    summary = self._format_tool_result_summary(tool, ok, data)
                    self._push_chat_log(f"{icon} 工具执行{'成功' if ok else '失败'}: {tool} [结果] {summary}", style=style)
                elif et == "confirm_request":
                    # 交互确认提示（由后台线程发起）
                    cid = data.get("id")
                    msg = str(data.get("message") or "").strip()
                    if isinstance(cid, int):
                        self._pending_confirm_id = cid
                        self._pending_confirm_msg = msg
                        self._push_chat_log("⚠ 需要确认（输入 y/n 后回车）：", style="bold yellow")
                        if msg:
                            for ln in msg.splitlines()[:12]:
                                self._push_chat_log(f"  {ln}", style="yellow")
                        inp = self.query_one("#input", Input)
                        inp.placeholder = "确认：输入 y/n 后回车（y=允许，n=拒绝）"
                        try:
                            inp.focus()
                        except Exception:
                            pass
                        self._refresh_header_panel()

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
                if self._conversation_mode != "log":
                    # 对话区：结构化块
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
                if self._conversation_mode != "log":
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
                if self._conversation_mode != "log":
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
                # 记录一次 LLM 请求（规划）
                if self._active_llm_id is None:
                    self._llm_start(kind="planning", step_id=None, purpose="生成计划")
                    self._refresh_ops()
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
                if self._conversation_mode != "log":
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
                self._refresh_ops()
                return

            if et == "display":
                if self._conversation_mode != "log":
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
                # 记录一次 LLM 请求（执行步骤）
                if self._active_llm_id is None:
                    sid = str(data.get("step_id") or "") or None
                    self._llm_start(kind="execute_step", step_id=sid, purpose=(f"执行 {sid}" if sid else "执行步骤"))
                self._refresh_ops()
                if self._conversation_mode != "log":
                    conversation.write(Text("🤖 LLM 请求中...", style="dim"))
                    if self._follow:
                        conversation.scroll_end(animate=False)
                return

            if et == "llm_request_params":
                pt = data.get("prompt_tokens_est")
                if isinstance(pt, int) and pt >= 0:
                    self._llm_prompt = pt
                # 附加本次请求的参数（用于 ops 历史展示）
                try:
                    self._llm_attach_params(data)
                except Exception:
                    pass
                mc = data.get("messages_count")
                if isinstance(mc, int) and mc >= 0:
                    self._last_llm_messages = mc
                self._state = "EXECUTING"
                self._operation = "LLM 请求"
                self._active_tasks = 1
                self._refresh_header_panel()
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
                # 结算本次 LLM 请求耗时
                try:
                    self._llm_finish(data)
                except Exception:
                    pass
                self._refresh_header_panel()
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

        # 事件窗格已改为纯日志输出：不再支持 Tree 的展开/收起交互

        def on_input_submitted(self, event: Input.Submitted) -> None:
            txt = (event.value or "").strip()
            self.query_one("#input", Input).value = ""
            if not txt:
                return

            # confirm 模式：优先消费输入（即使 _busy=True）
            if self._pending_confirm_id is not None:
                v = txt.strip().lower()
                allow = v in {"y", "yes", "允许", "是", "确认", "ok"}
                deny = v in {"n", "no", "拒绝", "否", "取消", "cancel"}
                if not (allow or deny):
                    self.query_one("#events", _Log).write(Text("请输入 y 或 n（确认模式）", style="yellow"))
                    return
                cid = self._pending_confirm_id
                with _confirm_lock:
                    waiter = _confirm_waiters.get(cid)
                    if waiter is not None:
                        waiter["allow"] = bool(allow)
                        ev0: threading.Event = waiter["event"]
                        ev0.set()
                self._push_chat_log(f"confirm: {'允许' if allow else '拒绝'}", style="green" if allow else "red")
                self._pending_confirm_id = None
                self._pending_confirm_msg = None
                inp = self.query_one("#input", Input)
                inp.placeholder = self._input_placeholder_normal
                try:
                    inp.focus()
                except Exception:
                    pass
                self._refresh_header_panel()
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
                    # 交互确认：后台线程阻塞等待 UI 输入 y/n
                    nonlocal _confirm_seq
                    with _confirm_lock:
                        cid = int(_confirm_seq)
                        _confirm_seq += 1
                        ev0 = threading.Event()
                        _confirm_waiters[cid] = {"event": ev0, "allow": None, "msg": _msg}
                    try:
                        q.put_nowait({"event": "confirm_request", "data": {"id": cid, "message": _msg}})
                    except Exception:
                        # UI 队列写失败：兜底拒绝
                        with _confirm_lock:
                            _confirm_waiters.pop(cid, None)
                        return False
                    # 等待用户输入（默认不超时；防止卡死可加上限）
                    ok = ev0.wait(timeout=60 * 30)
                    with _confirm_lock:
                        allow = bool((_confirm_waiters.get(cid) or {}).get("allow")) if ok else False
                        _confirm_waiters.pop(cid, None)
                    return bool(allow)

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



