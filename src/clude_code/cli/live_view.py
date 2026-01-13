from __future__ import annotations

import json
import time
from collections import deque
from typing import Any

from rich.console import Console
from rich.table import Table
from rich.text import Text


class LiveDisplay:
    """
    负责 50 行 Rich Live 界面渲染与状态管理。
    大文件治理说明：将视觉展现与命令逻辑解耦。
    """

    TOTAL_ROWS = 50
    ARCH_ROWS = 8
    DIV_ROWS = 1
    THOUGHT_HEADER_ROWS = 1
    THOUGHT_ROWS = 16
    GAP_ROWS = 1
    OPS_HEADER_ROWS = 1

    def __init__(self, console: Console, cfg: Any):
        self.console = console
        self.cfg = cfg
        self.t0 = time.time()
        self.last_step: int | str = "-"
        self.last_event = "等待"
        self.active_state = "IDLE"
        self.active_component = "orchestrator"

        # UI 状态行
        self.rows: dict[str, Text] = {
            "orchestrator": Text("（等待）", style="dim"),
            "planner": Text("（MVP：未独立实现；当前为 ReAct）", style="dim"),
            "context": Text("（等待）", style="dim"),
            "llm": Text("（等待）", style="dim"),
            "fs": Text("（等待）", style="dim"),
            "shell": Text("（等待）", style="dim"),
            "git": Text("（未触发）", style="dim"),
            "verify": Text("（未触发）", style="dim"),
        }

        # 操作快照
        self.op_llm_req_obj: dict = {}
        self.op_llm_resp_obj: dict = {}
        self.op_tool_call_obj: dict = {}
        self.op_tool_result_obj: dict = {}
        self.op_confirm = "（未触发）"
        self.op_policy = "（未触发）"
        self.op_autofix: deque[str] = deque(["（暂无）"], maxlen=5)
        self.thought_lines: deque[str] = deque(["（等待模型思考输出）"] * self.THOUGHT_ROWS, maxlen=self.THOUGHT_ROWS)

    def on_event(self, e: dict[str, Any]) -> None:
        """更新 UI 状态。"""
        self.last_step = e.get("step", "?")
        ev = str(e.get("event", ""))
        data = e.get("data", {}) or {}
        self.last_event = ev

        elapsed = int(time.time() - self.t0)
        self._set_row("orchestrator", f"step={self.last_step} event={self.last_event} 耗时={elapsed}s", style="white")

        if ev == "user_message":
            self.active_state = "INTAKE"
            self.active_component = "orchestrator"
            self._set_row("context", "接收用户输入，准备构建上下文…", style="dim")
            self.thought_lines.clear()
            for _ in range(self.THOUGHT_ROWS):
                self.thought_lines.append("（等待模型思考输出）")
            self.op_llm_req_obj = {}
            self.op_llm_resp_obj = {}
            self.op_tool_call_obj = {}
            self.op_tool_result_obj = {}
            self.op_confirm = "（未触发）"
            self.op_policy = "（未触发）"
            self.op_autofix.clear()
            self.op_autofix.append("（暂无）")

        elif ev == "llm_request":
            self.active_component = "llm"
            self._set_row("llm", f"请求 messages={data.get('messages')}", style="dim")
            self.op_llm_req_obj = {
                "base_url": self.cfg.llm.base_url,
                "api_mode": self.cfg.llm.api_mode,
                "model": self.cfg.llm.model or "auto",
                "temperature": self.cfg.llm.temperature,
                "max_tokens": self.cfg.llm.max_tokens,
                "messages_count": data.get("messages"),
                "stream": False,
            }

        elif ev == "llm_response":
            self.active_component = "llm"
            txt = self._clean_one_line(str(data.get("text", "")), 140)
            self._set_row("llm", f"响应: {txt}", style="white")
            raw_text = str(data.get("text", ""))
            self.op_llm_resp_obj = {
                "text_preview": self._clean_one_line(raw_text, 320),
                "text_length": len(raw_text),
                "truncated": bool(data.get("truncated", False)),
                "has_tool_call": "tool" in raw_text.lower() and "args" in raw_text.lower(),
            }
            # 提取思考内容
            block = self._extract_thought(raw_text)
            if block:
                self._push_thought_block(block)
            if any(k in txt for k in ("计划", "步骤", "Todo", "TODO")):
                self.active_state = "PLANNING"
                self.active_component = "planner"
                self._set_row("planner", "检测到规划输出（MVP：未独立 Planner，仅提示）", style="yellow")

        elif ev == "tool_call_parsed":
            tool = str(data.get("tool", ""))
            args = data.get("args", {}) or {}
            self.op_tool_call_obj = {"tool": tool, "args": args}
            self._route_tool_call(tool, args)

        elif ev == "tool_result":
            tool = str(data.get("tool", ""))
            ok = bool(data.get("ok"))
            err = data.get("error")
            payload = data.get("payload") or {}
            keys = list(payload.keys()) if isinstance(payload, dict) else []
            summary = f"{tool} ok={ok}"
            if err:
                summary += f" err={self._clean_one_line(str(err), 90)}"
            elif keys:
                summary += f" keys={keys[:6]}"
            self.op_tool_result_obj = {"tool": tool, "ok": ok, "error": err, "payload_keys": keys[:12]}
            self._push_fix_info(tool, ok, err, payload)
            self._route_tool_result(tool, ok, summary)
            self._push_thought_block(f"[{tool}] ok={ok}{' err' if err else ''}")

        elif ev in {"confirm_write", "confirm_exec"}:
            tool = str(data.get("tool", ""))
            allow = data.get("allow")
            msg = f"{ev} tool={tool} allow={allow}"
            self.op_confirm = self._clean_one_line(msg, 180)
            target = "fs" if ev == "confirm_write" else "shell"
            self._set_row(target, msg, style="yellow")
            self._push_thought_block(f"[confirm] {msg}")

        elif ev == "policy_deny_cmd":
            self.active_component = "shell"
            cmd_text = self._clean_one_line(str(data.get("command", "")), 120)
            self._set_row("shell", f"策略拒绝: {cmd_text}", style="red")
            self.op_policy = self._clean_one_line(str(data.get("command", "")), 180)
            self._push_thought_block("[policy] 策略拒绝命令")
            self._push_fix("已触发策略拒绝：请改用更安全/更窄范围的命令（优先只读命令）")

        elif ev == "stuttering_detected":
            self.active_component = "llm"
            self._set_row("llm", "输出异常：检测到重复字符，已截断", style="red")
            self.op_policy = "输出异常：重复字符，已截断"
            self._push_thought_block("[llm] 输出异常：重复字符，已截断")
            self._push_fix("已自动截断复读输出：建议缩小任务/降低 max_tokens/提高结构化约束")

        elif ev == "final_text":
            self.active_state = "SUMMARIZING"
            self.active_component = "orchestrator"

    def render(self) -> Table:
        """生成最终渲染的 Table。"""
        pct = self._component_percent(self.active_state)
        arch = self._render_arch(pct)
        div = [(Text(), Text("─" * 90, style="dim"))] * self.DIV_ROWS
        thought = self._render_thought()
        gap = [(Text(), Text("", style="dim"))] * self.GAP_ROWS
        ops = self._render_ops()

        panel = [*arch, *div, *thought, *gap, *ops]
        panel = panel[: self.TOTAL_ROWS]
        while len(panel) < self.TOTAL_ROWS:
            panel.append((Text(), Text("", style="dim")))

        t = Table(show_header=False, show_edge=False, pad_edge=False, box=None)
        t.add_column(justify="left", no_wrap=True, overflow="ellipsis")
        for left, right in panel:
            line = Text.assemble(left, " ", right) if left.plain.strip() else right
            t.add_row(line)
        return t

    # --- 内部逻辑辅助 ---

    def _set_row(self, key: str, text: str, *, style: str = "white") -> None:
        self.rows[key] = Text(self._clean_one_line(text, 160), style=style)

    def _clean_one_line(self, s: str, limit: int) -> str:
        s = s.replace("\n", " ").replace("\r", " ").strip()
        return s if len(s) <= limit else (s[: limit - 1] + "…")

    def _push_thought_block(self, block: str) -> None:
        block = (block or "").strip()
        if not block:
            return
        for ln in block.splitlines():
            ln = ln.strip()
            if not ln:
                continue
            self.thought_lines.append(self._clean_one_line(ln, 160))

    def _push_fix(self, msg: str) -> None:
        if not msg:
            return
        if len(self.op_autofix) == 1 and self.op_autofix[0] == "（暂无）":
            self.op_autofix.clear()
        self.op_autofix.append(self._clean_one_line(msg, 180))

    def _component_percent(self, state: str) -> int:
        return {
            "IDLE": 0,
            "INTAKE": 15,
            "CONTEXT_BUILDING": 50,
            "PLANNING": 60,
            "EXECUTING": 75,
            "VERIFYING": 90,
            "SUMMARIZING": 98,
            "DONE": 100,
        }.get(state, 50)

    def _bracket(self, label: str, key: str) -> Text:
        t = Text()
        style = "bold black on cyan" if self.active_component == key else "bold"
        t.append(f"[{label}]", style=style)
        return t

    def _extract_thought(self, text: str) -> str:
        if not text:
            return ""
        lo = text.lower()
        start = lo.find("<thought>")
        end = lo.find("</thought>")
        if start != -1 and end != -1 and end > start:
            return text[start + len("<thought>") : end].strip()
        
        lines = [ln.rstrip() for ln in text.splitlines()]
        keep: list[str] = []
        for ln in lines:
            if any(k in ln for k in ("【当前任务】", "【已知信息】", "【逻辑推演】", "【下一步动作】")):
                keep.append(ln.strip())
            elif keep and ln.strip().startswith(("【", "<", "{")):
                break
            elif keep and ln.strip():
                keep.append(ln.strip())
        return "\n".join(keep).strip()

    def _render_arch(self, pct: int) -> list[tuple[Text, Text]]:
        elapsed = int(time.time() - self.t0)
        arch: list[tuple[Text, Text]] = []
        arch.append((Text(), Text(f"系统架构（实时）  step={self.last_step}  event={self.last_event}  耗时={elapsed}s", style="bold cyan")))
        arch.append((Text(), Text("用户输入 → 编排器 → 规划器 → 上下文引擎 → 大语言引擎 → 工具执行 → 测试/验证", style="white")))
        
        l2 = Text("编排器 → ", style="white")
        l2.append_text(self._bracket("规划器", "planner"))
        l2.append(" → ")
        l2.append_text(self._bracket("上下文引擎", "context"))
        l2.append(" → ")
        l2.append_text(self._bracket("大语言引擎", "llm"))
        arch.append((Text(), l2))

        l3 = Text()
        l3.append_text(self._bracket("文件系统", "fs"))
        l3.append("  ")
        l3.append_text(self._bracket("Shell", "shell"))
        l3.append("  ")
        l3.append_text(self._bracket("Git-workflow", "git"))
        l3.append("  ")
        l3.append_text(self._bracket("测试/验证", "verify"))
        arch.append((Text(), l3))

        arch.append((Text(), Text("状态机（启发式）:", style="white")))
        arch.append((Text(), Text("INTAKE → CONTEXT_BUILDING → PLANNING → EXECUTING → VERIFYING → SUMMARIZING", style="white")))
        arch.append((Text(), Text("接收   →     构建上下文    →   规划   →    执行   →    验证    →   总结", style="dim")))
        arch.append((Text(), Text(f"当前状态: {self.active_state}   当前组件: {self.active_component}:{pct}%", style="yellow")))
        return arch

    def _render_thought(self) -> list[tuple[Text, Text]]:
        thought: list[tuple[Text, Text]] = []
        thought.append((Text(), Text("思考输出 （滑动窗口）", style="bold cyan")))
        for ln in list(self.thought_lines):
            thought.append((Text(), Text(ln, style="white")))
        while len(thought) < (self.THOUGHT_HEADER_ROWS + self.THOUGHT_ROWS):
            thought.append((Text(), Text("", style="dim")))
        return thought[: self.THOUGHT_HEADER_ROWS + self.THOUGHT_ROWS]

    def _render_ops(self) -> list[tuple[Text, Text]]:
        ops: list[tuple[Text, Text]] = []
        ops.append((Text(), Text("操作信息：", style="bold cyan")))
        
        # LLM Request
        ops.append((Text(), Text("请求大模型参数：", style="bold")))
        if self.op_llm_req_obj:
            for k in ("model", "temperature", "max_tokens"):
                if k in self.op_llm_req_obj:
                    ops.append((Text(), Text(f"  {k}: {self.op_llm_req_obj[k]}", style="white")))
            for k in ("api_mode", "stream", "messages_count", "base_url"):
                if k in self.op_llm_req_obj:
                    ops.append((Text(), Text(f"  {k}: {self.op_llm_req_obj[k]}", style="dim")))
        else:
            ops.append((Text(), Text("  （等待）", style="dim")))
        
        ops.append((Text(), Text("", style="dim")))
        ops.append((Text(), Text("大模型返回数据：", style="bold magenta")))
        if self.op_llm_resp_obj:
            if "text_preview" in self.op_llm_resp_obj:
                preview = self._clean_one_line(str(self.op_llm_resp_obj["text_preview"]), 120)
                ops.append((Text(), Text(f"  text_preview: \"{preview}\"", style="white")))
            for k in ("text_length", "truncated", "has_tool_call"):
                if k in self.op_llm_resp_obj:
                    ops.append((Text(), Text(f"  {k}: {self.op_llm_resp_obj[k]}", style="dim")))
        else:
            ops.append((Text(), Text("  （等待）", style="dim")))

        ops.append((Text(), Text("", style="dim")))
        ops.append((Text(), Text("工具执行：", style="bold yellow")))
        for ln in self._json_lines(self.op_tool_call_obj, max_lines=4):
            ops.append((Text(), Text("  " + ln, style="white")))
        
        ops.append((Text(), Text("", style="dim")))
        ops.append((Text(), Text("工具结果：", style="bold yellow")))
        for ln in self._json_lines(self.op_tool_result_obj, max_lines=4):
            ops.append((Text(), Text("  " + ln, style="white")))

        ops.append((Text(), Text("", style="dim")))
        ops.append((Text(), Text("自动修复操作：", style="bold cyan")))
        for ln in list(self.op_autofix):
            ops.append((Text(), Text("  - " + ln, style="white")))

        ops.append((Text(), Text("", style="dim")))
        ops.append((Text(), Text(f"确认/授权：{self.op_confirm}", style="white")))
        ops.append((Text(), Text(f"策略/拒绝：{self.op_policy}", style="white")))
        return ops

    def _json_lines(self, obj: dict, *, max_lines: int) -> list[str]:
        if not obj:
            return ["（等待）"]
        try:
            s = json.dumps(self._shrink_obj(obj), ensure_ascii=False, indent=2)
        except Exception:
            s = json.dumps({"_raw": self._clean_one_line(str(obj), 240)}, ensure_ascii=False, indent=2)
        lines = s.splitlines()
        if len(lines) <= max_lines:
            return lines
        return [*lines[: max(2, max_lines - 3)], "  ...", *lines[-2:]]

    def _shrink_obj(self, x: object, *, max_str: int = 240, max_list: int = 8) -> object:
        if x is None: return None
        if isinstance(x, (int, float, bool)): return x
        if isinstance(x, str):
            s = x.replace("\r", " ").replace("\n", " ")
            return s if len(s) <= max_str else (s[: max_str - 1] + "…")
        if isinstance(x, list):
            out = [self._shrink_obj(i, max_str=max_str, max_list=max_list) for i in x[:max_list]]
            if len(x) > max_list: out.append(f"...(+{len(x) - max_list})")
            return out
        if isinstance(x, dict):
            out_d: dict = {}
            for k, v in list(x.items())[:50]:
                out_d[str(k)] = self._shrink_obj(v, max_str=max_str, max_list=max_list)
            if len(x) > 50: out_d["..."] = f"+{len(x) - 50} keys"
            return out_d
        return self._clean_one_line(str(x), max_str)

    def _route_tool_call(self, tool: str, args: dict) -> None:
        if tool in {"grep", "read_file", "glob_file_search", "search_semantic", "list_dir"}:
            self.active_state = "CONTEXT_BUILDING"
            self.active_component = "context"
            brief = ""
            for k in ("path", "glob_pattern", "pattern", "query"):
                if k in args:
                    brief = f"{k}={self._clean_one_line(str(args.get(k)), 90)}"
                    break
            self._set_row("context", f"{tool} {brief}".rstrip(), style="cyan")

        if tool in {"list_dir", "read_file", "write_file", "apply_patch", "undo_patch", "glob_file_search"}:
            self.active_component = "fs"
            if tool in {"write_file", "apply_patch", "undo_patch"}:
                self.active_state = "EXECUTING"
            brief = ""
            if "path" in args:
                brief = f"path={self._clean_one_line(str(args.get('path')), 90)}"
            elif "glob_pattern" in args:
                brief = f"glob={self._clean_one_line(str(args.get('glob_pattern')), 90)}"
            self._set_row("fs", f"{tool} {brief}".rstrip(), style="yellow")

        if tool == "run_cmd":
            self.active_component = "shell"
            self.active_state = "EXECUTING"
            cmd = self._clean_one_line(str(args.get("command", "")), 120)
            self._set_row("shell", f"run_cmd {cmd}", style="yellow")
            low = cmd.strip().lower()
            if low.startswith("git "):
                self.active_component = "git"
                self._set_row("git", f"git: {cmd}", style="cyan")
            if any(x in low for x in ("pytest", "npm test", "cargo test", "go test")):
                self.active_component = "verify"
                self.active_state = "VERIFYING"
                self._set_row("verify", f"测试/验证: {cmd}", style="cyan")

    def _route_tool_result(self, tool: str, ok: bool, summary: str) -> None:
        style = "green" if ok else "red"
        if tool in {"list_dir", "read_file", "write_file", "apply_patch", "undo_patch", "glob_file_search"}:
            self._set_row("fs", summary, style=style)
        elif tool in {"grep", "search_semantic"}:
            self._set_row("context", summary, style=style)
        elif tool == "run_cmd":
            self._set_row("shell", summary, style=style)
        else:
            self._set_row("orchestrator", summary, style=style)

    def _push_fix_info(self, tool: str, ok: bool, err: Any, payload: dict) -> None:
        if tool == "grep" and isinstance(payload, dict):
            eng = payload.get("engine")
            if eng == "python": self._push_fix("grep 已回退到 Python 引擎（建议安装 rg：运行 `clude doctor --fix`）")
            elif eng == "rg": self._push_fix("grep 使用 rg 引擎（更快且输出更稳定）")
        if tool == "read_file" and isinstance(payload, dict) and payload.get("truncated"):
            self._push_fix("read_file 内容被截断：已摘要回喂；可用 grep/search_semantic 精确定位后再分段读取")
        if tool in {"apply_patch", "undo_patch"} and not ok:
            self._push_fix("补丁/回滚失败：建议先 read_file 确认目标段落，再扩大 old/new 上下文或降低 fuzzy")
        if not ok and isinstance(err, dict):
            msg = str(err.get("message", "")).lower()
            if "not found" in msg: self._push_fix("路径不存在：建议先 list_dir 或 glob_file_search 确认真实路径")
            if "ctags" in msg: self._push_fix("ctags 失败：建议 `clude doctor --fix` 安装 universal-ctags")
            if "rg" in msg or "ripgrep" in msg: self._push_fix("rg 失败：建议 `clude doctor --fix` 安装 ripgrep")

