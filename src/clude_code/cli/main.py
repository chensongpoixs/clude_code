import shutil
import sys
import subprocess
import time
from collections import deque
from pathlib import Path
import json

import typer
from rich.console import Console
from rich.live import Live
from rich.prompt import Confirm
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text

from clude_code.config import CludeConfig
from clude_code.orchestrator.agent_loop import AgentLoop

app = typer.Typer(help="clude: a Claude Code-like local code agent CLI (Python).")
console = Console()


@app.command()
def version() -> None:
    """Print CLI version."""
    from clude_code import __version__

    typer.echo(__version__)


@app.command()
def chat(
    model: str = typer.Option("", help="指定 llama.cpp 的 model id（openai_compat 常需要）"),
    select_model: bool = typer.Option(False, "--select-model", help="启动时从 /v1/models 交互选择 model（openai_compat）"),
    debug: bool = typer.Option(False, "--debug", help="显示 Agent 可观测执行轨迹（LLM输出/工具调用/确认/结果）并写入 .clude/logs/trace.jsonl"),
    live: bool = typer.Option(False, "--live", help="执行过程中固定 50 行实时刷新：上半系统架构/状态机/操作信息，下半思考滚动（不刷屏；开启后会自动启用 --debug）"),
) -> None:
    """
    Start an interactive session (MVP placeholder).

    In MVP you will wire this to:
    - orchestrator state machine
    - tooling registry
    - policy confirmations
    - audit logging
    """
    console.print("[bold]进入 clude chat（llama.cpp HTTP）[/bold]")
    console.print("- 输入 `exit` 退出")
    console.print("- 工具写文件/执行命令默认需要确认")

    cfg = CludeConfig()
    if model:
        cfg.llm.model = model

    if select_model and cfg.llm.api_mode == "openai_compat":
        from clude_code.llm.llama_cpp_http import LlamaCppHttpClient

        client = LlamaCppHttpClient(
            base_url=cfg.llm.base_url,
            api_mode="openai_compat",
            model=cfg.llm.model,
            temperature=0.0,
            max_tokens=8,
            timeout_s=cfg.llm.timeout_s,
        )
        ids = client.list_model_ids()
        if not ids:
            console.print("[yellow]未能从 /v1/models 获取模型列表（可能不支持）。[/yellow]")
        else:
            console.print("[bold]可用模型（/v1/models）[/bold]")
            for i, mid in enumerate(ids, start=1):
                console.print(f"{i}. {mid}")
            sel = Prompt.ask("请选择模型序号", default="1")
            try:
                idx = int(sel)
                cfg.llm.model = ids[idx - 1]
            except Exception:
                console.print("[yellow]选择无效，继续使用默认/自动 model。[/yellow]")
    agent = AgentLoop(cfg)

    def _confirm(msg: str) -> bool:
        return Confirm.ask(msg, default=False)

    def _clean_one_line(s: str, limit: int) -> str:
        s = s.replace("\n", " ").replace("\r", " ").strip()
        return s if len(s) <= limit else (s[: limit - 1] + "…")

    def _extract_thought(text: str) -> str:
        """
        Best-effort extraction of the agent's 'thought' section for live scrolling display.
        Supports:
        - <thought>...</thought>
        - fallback: lines containing '【当前任务】/【逻辑推演】/【下一步动作】'
        """
        if not text:
            return ""
        t = text
        # Prefer explicit <thought> block
        lo = t.lower()
        start = lo.find("<thought>")
        end = lo.find("</thought>")
        if start != -1 and end != -1 and end > start:
            inner = t[start + len("<thought>") : end]
            return inner.strip()

        # Fallback: capture structured Chinese reasoning if present
        lines = [ln.rstrip() for ln in t.splitlines()]
        keep: list[str] = []
        for ln in lines:
            if any(k in ln for k in ("【当前任务】", "【已知信息】", "【当前已知】", "【逻辑推演】", "【下一步动作】")):
                keep.append(ln.strip())
            elif keep and ln.strip().startswith(("【", "<", "{")):
                # Stop when we reach a new block (tool JSON / tag / etc.)
                break
            elif keep and ln.strip():
                keep.append(ln.strip())
        return "\n".join(keep).strip()

    def _render_live(panel_rows: list[tuple[Text, Text]]) -> Table:
        """
        Render a fixed-size live panel (no scroll), continuously refreshed in-place.
        """
        # Render as a single-column "monitor screen" to match the requested layout.
        t = Table(show_header=False, show_edge=False, pad_edge=False, box=None)
        t.add_column(justify="left", no_wrap=True, overflow="ellipsis")
        for left, right in panel_rows:
            # keep compatibility: callers pass (left,right), but we display as one line
            if left.plain.strip():
                line = Text.assemble(left, " ", right)
            else:
                line = right
            t.add_row(line)
        return t

    while True:
        user_text = typer.prompt("you")
        if user_text.strip().lower() in {"exit", "quit"}:
            console.print("bye")
            return

        if live:
            debug = True
            t0 = time.time()
            last_step: int | str = "-"
            last_event = "等待"
            active_state = "IDLE"
            active_component = "orchestrator"

            # Fixed size requirement
            TOTAL_ROWS = 50
            ARCH_ROWS = 8  # 增加1行：状态机中文行
            DIV_ROWS = 1
            # Requested order: divider -> 思考滑动窗口 -> 操作信息(含多行 JSON)
            THOUGHT_HEADER_ROWS = 1
            # 给“操作信息（含 JSON + 自动修复）”留足空间；思考窗口依旧是滚动的
            THOUGHT_ROWS = 16
            GAP_ROWS = 1
            OPS_HEADER_ROWS = 1
            OPS_ROWS = TOTAL_ROWS - ARCH_ROWS - DIV_ROWS - THOUGHT_HEADER_ROWS - THOUGHT_ROWS - GAP_ROWS - OPS_HEADER_ROWS
            OPS_ROWS = max(12, OPS_ROWS)

            def _left(label: str, style: str) -> Text:
                t = Text()
                t.append(label, style=style)
                return t

            def _component_percent(state: str) -> int:
                # heuristic progress mapping (MVP)
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

            def _bracket(label: str, key: str) -> Text:
                t = Text()
                if active_component == key:
                    t.append(f"[{label}]", style="bold black on cyan")
                else:
                    t.append(f"[{label}]", style="bold")
                return t

            rows: dict[str, Text] = {
                "orchestrator": Text("（等待）", style="dim"),
                "planner": Text("（MVP：未独立实现；当前为 ReAct）", style="dim"),
                "context": Text("（等待）", style="dim"),
                "llm": Text("（等待）", style="dim"),
                "fs": Text("（等待）", style="dim"),
                "shell": Text("（等待）", style="dim"),
                "git": Text("（未触发）", style="dim"),
                "verify": Text("（未触发）", style="dim"),
            }

            # Ops area: keep last snapshots (compact)
            op_llm_req_obj: dict = {}
            op_llm_resp_obj: dict = {}
            op_tool_call_obj: dict = {}
            op_tool_result_obj: dict = {}
            op_confirm = "（未触发）"
            op_policy = "（未触发）"
            # 自动修复操作信息（最近 N 条）
            op_autofix = deque(["（暂无）"], maxlen=5)

            thought_lines = deque(["（等待模型思考输出）"] * THOUGHT_ROWS, maxlen=THOUGHT_ROWS)

            def _set_row(key: str, text: str, *, style: str = "white") -> None:
                rows[key] = Text(_clean_one_line(text, 160), style=style)

            def _push_thought_block(block: str) -> None:
                block = (block or "").strip()
                if not block:
                    return
                for ln in block.splitlines():
                    ln = ln.strip()
                    if not ln:
                        continue
                    thought_lines.append(_clean_one_line(ln, 160))

            def _panel_rows() -> list[tuple[Text, Text]]:
                elapsed = int(time.time() - t0)
                pct = _component_percent(active_state)

                # --- Architecture area (exactly ARCH_ROWS) ---
                arch: list[tuple[Text, Text]] = []
                arch.append((_left("", "dim"), Text(f"系统架构（实时）  step={last_step}  event={last_event}  耗时={elapsed}s", style="bold cyan")))
                arch.append((_left("", "dim"), Text("用户输入 → 编排器 → 规划器 → 上下文引擎 → 大语言引擎 → 工具执行 → 测试/验证", style="white")))

                l2 = Text()
                l2.append("编排器 → ", style="white")
                l2.append_text(_bracket("规划器", "planner"))
                l2.append(" → ")
                l2.append_text(_bracket("上下文引擎", "context"))
                l2.append(" → ")
                l2.append_text(_bracket("大语言引擎", "llm"))
                arch.append((_left("", "dim"), l2))

                l3 = Text()
                l3.append_text(_bracket("文件系统", "fs"))
                l3.append("  ")
                l3.append_text(_bracket("Shell", "shell"))
                l3.append("  ")
                l3.append_text(_bracket("Git-workflow", "git"))
                l3.append("  ")
                l3.append_text(_bracket("测试/验证", "verify"))
                arch.append((_left("", "dim"), l3))

                arch.append((_left("", "dim"), Text("状态机（启发式）:", style="white")))
                arch.append((_left("", "dim"), Text("INTAKE → CONTEXT_BUILDING → PLANNING → EXECUTING → VERIFYING → SUMMARIZING", style="white")))
                arch.append((_left("", "dim"), Text("接收   →     构建上下文    →   规划   →    执行   →    验证    →   总结", style="dim")))
                arch.append((_left("", "dim"), Text(f"当前状态: {active_state}   当前组件: {active_component}:{pct}%", style="yellow")))

                # Ensure exact arch size
                arch = arch[:ARCH_ROWS] + [(_left("", "dim"), Text("", style="dim"))] * max(0, ARCH_ROWS - len(arch))

                # Divider
                div = [(_left("", "dim"), Text("─" * 90, style="dim"))] * DIV_ROWS

                # --- Thought area (requested BEFORE ops) ---
                thought: list[tuple[Text, Text]] = []
                thought.append((_left("", "dim"), Text("思考输出 （滑动窗口）", style="bold cyan")))
                # Display thought lines directly without JSON code block markers
                for ln in list(thought_lines):
                    thought.append((_left("", "dim"), Text(ln, style="white")))
                thought = thought[: (THOUGHT_HEADER_ROWS + THOUGHT_ROWS)]
                while len(thought) < (THOUGHT_HEADER_ROWS + THOUGHT_ROWS):
                    thought.append((_left("", "dim"), Text("", style="dim")))

                gap = [(_left("", "dim"), Text("", style="dim"))] * GAP_ROWS

                def _shrink_obj(x: object, *, max_str: int = 240, max_list: int = 8) -> object:
                    if x is None:
                        return None
                    if isinstance(x, (int, float, bool)):
                        return x
                    if isinstance(x, str):
                        s = x.replace("\r", " ").replace("\n", " ")
                        return s if len(s) <= max_str else (s[: max_str - 1] + "…")
                    if isinstance(x, list):
                        out = [_shrink_obj(i, max_str=max_str, max_list=max_list) for i in x[:max_list]]
                        if len(x) > max_list:
                            out.append(f"...(+{len(x) - max_list})")
                        return out
                    if isinstance(x, dict):
                        out: dict = {}
                        for k, v in list(x.items())[:50]:
                            out[str(k)] = _shrink_obj(v, max_str=max_str, max_list=max_list)
                        if len(x) > 50:
                            out["..."] = f"+{len(x) - 50} keys"
                        return out
                    return _clean_one_line(str(x), max_str)

                def _json_lines(obj: dict, *, max_lines: int) -> list[str]:
                    if not obj:
                        return ["（等待）"]
                    try:
                        s = json.dumps(_shrink_obj(obj), ensure_ascii=False, indent=2)
                    except Exception:
                        s = json.dumps({"_raw": _clean_one_line(str(obj), 240)}, ensure_ascii=False, indent=2)
                    lines = s.splitlines()
                    if len(lines) <= max_lines:
                        return lines
                    # keep head+tail
                    head = lines[: max(2, max_lines - 3)]
                    tail = lines[-2:]
                    return [*head, "  ...", *tail]

                # --- Ops area (with multi-line JSON blocks) ---
                ops: list[tuple[Text, Text]] = []
                ops.append((_left("", "dim"), Text("操作信息：", style="bold cyan")))

                ops.append((_left("", "dim"), Text("请求大模型参数：", style="bold")))
                if op_llm_req_obj:
                    if op_llm_req_obj.get("model"):
                        ops.append((_left("", "dim"), Text(f"  model: {op_llm_req_obj.get('model')}", style="white")))
                    if op_llm_req_obj.get("temperature") is not None:
                        ops.append((_left("", "dim"), Text(f"  temperature: {op_llm_req_obj.get('temperature')}", style="white")))
                    if op_llm_req_obj.get("max_tokens"):
                        ops.append((_left("", "dim"), Text(f"  max_tokens: {op_llm_req_obj.get('max_tokens')}", style="white")))
                    if op_llm_req_obj.get("api_mode"):
                        ops.append((_left("", "dim"), Text(f"  api_mode: {op_llm_req_obj.get('api_mode')}", style="dim")))
                    if op_llm_req_obj.get("stream") is not None:
                        ops.append((_left("", "dim"), Text(f"  stream: {op_llm_req_obj.get('stream')}", style="dim")))
                    if op_llm_req_obj.get("messages_count"):
                        ops.append((_left("", "dim"), Text(f"  messages_count: {op_llm_req_obj.get('messages_count')}", style="dim")))
                    if op_llm_req_obj.get("base_url"):
                        ops.append((_left("", "dim"), Text(f"  base_url: {op_llm_req_obj.get('base_url')}", style="dim")))
                else:
                    ops.append((_left("", "dim"), Text("  （等待）", style="dim")))
                ops.append((_left("", "dim"), Text("", style="dim")))

                ops.append((_left("", "dim"), Text("大模型返回数据：", style="bold magenta")))
                if op_llm_resp_obj:
                    if op_llm_resp_obj.get("text_preview"):
                        preview = _clean_one_line(str(op_llm_resp_obj.get("text_preview", "")), 120)
                        ops.append((_left("", "dim"), Text(f"  text_preview: \"{preview}\"", style="white")))
                    if op_llm_resp_obj.get("text_length") is not None:
                        ops.append((_left("", "dim"), Text(f"  text_length: {op_llm_resp_obj.get('text_length')}", style="dim")))
                    if op_llm_resp_obj.get("truncated") is not None:
                        ops.append((_left("", "dim"), Text(f"  truncated: {op_llm_resp_obj.get('truncated')}", style="dim")))
                    if op_llm_resp_obj.get("has_tool_call") is not None:
                        ops.append((_left("", "dim"), Text(f"  has_tool_call: {op_llm_resp_obj.get('has_tool_call')}", style="dim")))
                else:
                    ops.append((_left("", "dim"), Text("  （等待）", style="dim")))
                ops.append((_left("", "dim"), Text("", style="dim")))

                ops.append((_left("", "dim"), Text("工具执行：", style="bold yellow")))
                for ln in _json_lines(op_tool_call_obj, max_lines=4):
                    ops.append((_left("", "dim"), Text("  " + ln, style="white")))
                ops.append((_left("", "dim"), Text("", style="dim")))

                ops.append((_left("", "dim"), Text("工具结果：", style="bold yellow")))
                for ln in _json_lines(op_tool_result_obj, max_lines=4):
                    ops.append((_left("", "dim"), Text("  " + ln, style="white")))

                ops.append((_left("", "dim"), Text("", style="dim")))
                ops.append((_left("", "dim"), Text("自动修复操作：", style="bold cyan")))
                for ln in list(op_autofix):
                    ops.append((_left("", "dim"), Text("  - " + ln, style="white")))

                # Add confirm/policy single-lines
                ops.append((_left("", "dim"), Text("", style="dim")))
                ops.append((_left("", "dim"), Text(f"确认/授权：{op_confirm}", style="white")))
                ops.append((_left("", "dim"), Text(f"策略/拒绝：{op_policy}", style="white")))

                # pad/truncate ops to OPS_HEADER_ROWS + OPS_ROWS
                while len(ops) < (OPS_HEADER_ROWS + OPS_ROWS):
                    ops.append((_left("", "dim"), Text("", style="dim")))
                ops = ops[: (OPS_HEADER_ROWS + OPS_ROWS)]

                panel = [*arch, *div, *thought, *gap, *ops]
                # enforce TOTAL_ROWS
                panel = panel[:TOTAL_ROWS]
                while len(panel) < TOTAL_ROWS:
                    panel.append((_left("", "dim"), Text("", style="dim")))
                return panel

            def _on_event(e: dict) -> None:
                nonlocal last_step, last_event, active_state, active_component
                nonlocal op_llm_req_obj, op_llm_resp_obj, op_tool_call_obj, op_tool_result_obj, op_confirm, op_policy, op_autofix
                step = e.get("step", "?")
                ev = str(e.get("event", ""))
                data = e.get("data", {}) or {}
                last_step = step
                last_event = ev

                elapsed = int(time.time() - t0)
                _set_row("orchestrator", f"step={last_step} event={last_event} 耗时={elapsed}s", style="white")

                if ev == "user_message":
                    active_state = "INTAKE"
                    active_component = "orchestrator"
                    _set_row("context", "接收用户输入，准备构建上下文…", style="dim")
                    thought_lines.clear()
                    for _ in range(THOUGHT_ROWS):
                        thought_lines.append("（等待模型思考输出）")
                    op_llm_req_obj = {}
                    op_llm_resp_obj = {}
                    op_tool_call_obj = {}
                    op_tool_result_obj = {}
                    op_confirm = "（未触发）"
                    op_policy = "（未触发）"
                    op_autofix.clear()
                    op_autofix.append("（暂无）")

                if ev == "llm_request":
                    active_component = "llm"
                    _set_row("llm", f"请求 messages={data.get('messages')}", style="dim")
                    op_llm_req_obj = {
                        "base_url": cfg.llm.base_url,
                        "api_mode": cfg.llm.api_mode,
                        "model": cfg.llm.model or "auto",
                        "temperature": cfg.llm.temperature,
                        "max_tokens": cfg.llm.max_tokens,
                        "messages_count": data.get("messages"),
                        "stream": False,
                    }

                elif ev == "llm_response":
                    active_component = "llm"
                    txt = _clean_one_line(str(data.get("text", "")), 140)
                    _set_row("llm", f"响应: {txt}", style="white")
                    raw_text = str(data.get("text", ""))
                    op_llm_resp_obj = {
                        "text_preview": _clean_one_line(raw_text, 320),
                        "text_length": len(raw_text),
                        "truncated": bool(data.get("truncated", False)),
                        "has_tool_call": "tool" in raw_text.lower() and "args" in raw_text.lower(),
                    }
                    # Feed thought scroll from the raw assistant output (may contain <thought>)
                    raw = str(data.get("text", ""))
                    block = _extract_thought(raw)
                    if block:
                        _push_thought_block(block)
                    # Heuristic: if model is producing a plan-ish response, reflect it.
                    if any(k in txt for k in ("计划", "步骤", "Todo", "TODO")):
                        active_state = "PLANNING"
                        active_component = "planner"
                        _set_row("planner", "检测到规划输出（MVP：未独立 Planner，仅提示）", style="yellow")

                elif ev == "tool_call_parsed":
                    tool = str(data.get("tool", ""))
                    args = data.get("args", {}) or {}
                    op_tool_call_obj = {"tool": tool, "args": args}

                    # Context engine activities
                    if tool in {"grep", "read_file", "glob_file_search", "search_semantic", "list_dir"}:
                        active_state = "CONTEXT_BUILDING"
                        active_component = "context"
                        brief = ""
                        for k in ("path", "glob_pattern", "pattern", "query"):
                            if k in args:
                                brief = f"{k}={_clean_one_line(str(args.get(k)), 90)}"
                                break
                        _set_row("context", f"{tool} {brief}".rstrip(), style="cyan")

                    # File system activities
                    if tool in {"list_dir", "read_file", "write_file", "apply_patch", "undo_patch", "glob_file_search"}:
                        active_component = "fs"
                        if tool in {"write_file", "apply_patch", "undo_patch"}:
                            active_state = "EXECUTING"
                        brief = ""
                        if "path" in args:
                            brief = f"path={_clean_one_line(str(args.get('path')), 90)}"
                        elif "glob_pattern" in args:
                            brief = f"glob={_clean_one_line(str(args.get('glob_pattern')), 90)}"
                        _set_row("fs", f"{tool} {brief}".rstrip(), style="yellow")

                    # Shell activities
                    if tool == "run_cmd":
                        active_component = "shell"
                        active_state = "EXECUTING"
                        cmd = _clean_one_line(str(args.get("command", "")), 120)
                        _set_row("shell", f"run_cmd {cmd}", style="yellow")
                        # Heuristic: classify git / tests from run_cmd
                        low = cmd.strip().lower()
                        if low.startswith("git "):
                            active_component = "git"
                            _set_row("git", f"git: {cmd}", style="cyan")
                        if any(x in low for x in ("pytest", "python -m pytest", "npm test", "pnpm test", "yarn test", "cargo test", "go test", "mvn test", "gradle test")):
                            active_component = "verify"
                            active_state = "VERIFYING"
                            _set_row("verify", f"测试/验证: {cmd}", style="cyan")

                elif ev == "tool_result":
                    tool = str(data.get("tool", ""))
                    ok = bool(data.get("ok"))
                    err = data.get("error")
                    payload = data.get("payload") or {}
                    keys = list(payload.keys()) if isinstance(payload, dict) else []

                    def _style(ok_: bool) -> str:
                        return "green" if ok_ else "red"

                    summary = f"{tool} ok={ok}"
                    if err:
                        summary += f" err={_clean_one_line(str(err), 90)}"
                    elif keys:
                        summary += f" keys={keys[:6]}"
                    op_tool_result_obj = {
                        "tool": tool,
                        "ok": ok,
                        "error": err,
                        "payload_keys": keys[:12],
                    }

                    # ---- 自动修复信息（启发式，重点是“我们做了什么/下一步怎么做”）----
                    def _push_fix(msg: str) -> None:
                        if not msg:
                            return
                        # 去掉“暂无”占位
                        if len(op_autofix) == 1 and op_autofix[0] == "（暂无）":
                            op_autofix.clear()
                        op_autofix.append(_clean_one_line(msg, 180))

                    # grep：展示 rg / python fallback
                    if tool == "grep" and isinstance(payload, dict):
                        eng = payload.get("engine")
                        if eng == "python":
                            _push_fix("grep 已回退到 Python 引擎（建议安装 rg：运行 `clude doctor --fix`）")
                        elif eng == "rg":
                            _push_fix("grep 使用 rg 引擎（更快且输出更稳定）")

                    # read_file：截断提示
                    if tool == "read_file" and isinstance(payload, dict) and payload.get("truncated"):
                        _push_fix("read_file 内容被截断：已摘要回喂；可用 grep/search_semantic 精确定位后再分段读取")

                    # apply_patch/undo_patch：失败提示
                    if tool in {"apply_patch", "undo_patch"} and not ok:
                        _push_fix("补丁/回滚失败：建议先 read_file 确认目标段落，再扩大 old/new 上下文或降低 fuzzy")

                    # 通用失败提示
                    if not ok and isinstance(err, dict):
                        code = str(err.get("code", ""))
                        msg = str(err.get("message", ""))
                        if code in {"E_NOT_FOUND", "E_NOT_DIR"} or "not found" in msg.lower():
                            _push_fix("路径不存在：建议先 list_dir 或 glob_file_search 确认真实路径")
                        if "ctags" in msg.lower():
                            _push_fix("ctags 失败：建议 `clude doctor --fix` 安装 universal-ctags")
                        if "rg" in msg.lower() or "ripgrep" in msg.lower():
                            _push_fix("rg 失败：建议 `clude doctor --fix` 安装 ripgrep")

                    # Route results to their subsystem line(s)
                    if tool in {"list_dir", "read_file", "write_file", "apply_patch", "undo_patch", "glob_file_search"}:
                        _set_row("fs", summary, style=_style(ok))
                    elif tool in {"grep", "search_semantic"}:
                        _set_row("context", summary, style=_style(ok))
                    elif tool == "run_cmd":
                        _set_row("shell", summary, style=_style(ok))
                    else:
                        _set_row("orchestrator", summary, style=_style(ok))
                    # Also append a short line into thought scroll for continuity
                    _push_thought_block(f"[{tool}] ok={ok}{' err' if err else ''}")

                elif ev in {"confirm_write", "confirm_exec"}:
                    tool = str(data.get("tool", ""))
                    allow = data.get("allow")
                    msg = f"{ev} tool={tool} allow={allow}"
                    op_confirm = _clean_one_line(msg, 180)
                    if ev == "confirm_write":
                        _set_row("fs", msg, style="yellow")
                    else:
                        _set_row("shell", msg, style="yellow")
                    _push_thought_block(f"[confirm] {msg}")

                elif ev == "policy_deny_cmd":
                    active_component = "shell"
                    _set_row("shell", f"策略拒绝: {_clean_one_line(str(data.get('command', '')), 120)}", style="red")
                    op_policy = _clean_one_line(str(data.get("command", "")), 180)
                    _push_thought_block("[policy] 策略拒绝命令")
                    if len(op_autofix) == 1 and op_autofix[0] == "（暂无）":
                        op_autofix.clear()
                    op_autofix.append("已触发策略拒绝：请改用更安全/更窄范围的命令（优先只读命令）")

                elif ev == "stuttering_detected":
                    active_component = "llm"
                    _set_row("llm", "输出异常：检测到重复字符，已截断", style="red")
                    op_policy = "输出异常：重复字符，已截断"
                    _push_thought_block("[llm] 输出异常：重复字符，已截断")
                    if len(op_autofix) == 1 and op_autofix[0] == "（暂无）":
                        op_autofix.clear()
                    op_autofix.append("已自动截断复读输出：建议缩小任务/降低 max_tokens/提高结构化约束")

                elif ev == "final_text":
                    active_state = "SUMMARIZING"
                    active_component = "orchestrator"

                try:
                    live_view.update(_render_live(_panel_rows()))
                except Exception:
                    pass

            # Keep final frame visible after the turn ends.
            with Live(_render_live(_panel_rows()), console=console, refresh_per_second=12, transient=False) as live_view:
                turn = agent.run_turn(user_text, confirm=_confirm, debug=debug, on_event=_on_event)
                active_state = "DONE"
                active_component = "orchestrator"
                last_event = "done"
                _push_thought_block("[done] 本轮结束，已固定显示最终状态与滑动窗口")
                try:
                    live_view.update(_render_live(_panel_rows()))
                except Exception:
                    pass
        else:
            turn = agent.run_turn(user_text, confirm=_confirm, debug=debug)

        console.print("\n[bold]assistant[/bold]")
        console.print(turn.assistant_text)
        if debug:
            console.print(f"[dim]trace_id={turn.trace_id}（详见 .clude/logs/trace.jsonl）[/dim]")
            if not live:
                console.print("[dim]--- agent 执行轨迹（可观测） ---[/dim]")
                for e in turn.events:
                    step = e.get("step")
                    ev = e.get("event")
                    data = e.get("data", {})
                    # 控制台展示做摘要，避免刷屏
                    if ev in {"llm_response", "final_text"}:
                        text = str(data.get("text", ""))
                        console.print(f"[dim]{step}. {ev}[/dim] {text[:240]}{'…' if len(text) > 240 else ''}")
                    elif ev == "tool_call_parsed":
                        console.print(f"[dim]{step}. tool[/dim] {data.get('tool')} args={data.get('args')}")
                    elif ev == "tool_result":
                        console.print(
                            f"[dim]{step}. result[/dim] tool={data.get('tool')} ok={data.get('ok')} "
                            f"error={data.get('error')} payload_keys={list((data.get('payload') or {}).keys())}"
                        )
                    else:
                        console.print(f"[dim]{step}. {ev}[/dim] {data}")
        console.print("")


@app.command()
def doctor(
    fix: bool = typer.Option(False, "--fix", help="尝试交互式自动修复缺失的依赖项")
) -> None:
    """Basic diagnostics: workspace + llama.cpp connectivity."""
    from clude_code.llm.llama_cpp_http import ChatMessage, LlamaCppHttpClient

    cfg = CludeConfig()
    console.print("[bold]clude doctor[/bold]")
    
    missing_tools = []

    # 1. 检查 rg
    rg = shutil.which("rg")
    console.print(f"- ripgrep (rg): {rg or '[red]NOT FOUND[/red]'}")
    if not rg:
        missing_tools.append("ripgrep")

    # 2. 检查 ctags
    ctags = shutil.which("ctags")
    console.print(f"- universal-ctags (ctags): {ctags or '[red]NOT FOUND[/red]'}")
    if not ctags:
        missing_tools.append("universal-ctags")

    if missing_tools and fix:
        console.print(f"\n[bold yellow]检测到缺失工具: {', '.join(missing_tools)}[/bold yellow]")
        _try_fix_missing_tools(missing_tools)
        # 修复后重新检查
        return doctor(fix=False)

    if missing_tools and not fix:
        console.print("\n[yellow]提示: 使用 `clude doctor --fix` 可尝试自动修复缺失工具。[/yellow]")

    console.print(f"\n- workspace_root: {cfg.workspace_root}")
    console.print(f"- llama base_url: {cfg.llm.base_url}")
    console.print(f"- llama api_mode: {cfg.llm.api_mode}")

    # workspace checks
    wr = Path(cfg.workspace_root)
    if not wr.exists():
        console.print("[red]workspace_root 不存在[/red]")
        raise typer.Exit(code=2)
    try:
        p = wr / ".clude" / "doctor.tmp"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("ok", encoding="utf-8")
        p.unlink(missing_ok=True)
        console.print("[green]workspace 可读写 OK[/green]")
    except Exception as e:
        console.print(f"[red]workspace 写入失败：{e}[/red]")
        raise typer.Exit(code=2)

    # llama connectivity
    try:
        client = LlamaCppHttpClient(
            base_url=cfg.llm.base_url,
            api_mode=cfg.llm.api_mode,  # type: ignore[arg-type]
            model=cfg.llm.model,
            temperature=0.0,
            max_tokens=32,
            timeout_s=cfg.llm.timeout_s,
        )
        if cfg.llm.api_mode == "openai_compat":
            mid = client.try_get_first_model_id()
            console.print(f"- openai_compat /v1/models first_id: {mid!r}")
        out = client.chat(
            [
                ChatMessage(role="system", content="你是诊断助手，只输出 OK。"),
                ChatMessage(role="user", content="ping"),
            ]
        ).strip()
        console.print(f"[green]llama.cpp 连通 OK[/green] response={out!r}")
    except Exception as e:
        console.print(f"[red]llama.cpp 连通失败：{e}[/red]")
        raise typer.Exit(code=3)

    # workspace checks
    wr = Path(cfg.workspace_root)
    if not wr.exists():
        console.print("[red]workspace_root 不存在[/red]")
        raise typer.Exit(code=2)
    try:
        p = wr / ".clude" / "doctor.tmp"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("ok", encoding="utf-8")
        p.unlink(missing_ok=True)
        console.print("[green]workspace 可读写 OK[/green]")
    except Exception as e:
        console.print(f"[red]workspace 写入失败：{e}[/red]")
        raise typer.Exit(code=2)

    # llama connectivity
    try:
        client = LlamaCppHttpClient(
            base_url=cfg.llm.base_url,
            api_mode=cfg.llm.api_mode,  # type: ignore[arg-type]
            model=cfg.llm.model,
            temperature=0.0,
            max_tokens=32,
            timeout_s=cfg.llm.timeout_s,
        )
        if cfg.llm.api_mode == "openai_compat":
            mid = client.try_get_first_model_id()
            console.print(f"- openai_compat /v1/models first_id: {mid!r}")
        out = client.chat(
            [
                ChatMessage(role="system", content="你是诊断助手，只输出 OK。"),
                ChatMessage(role="user", content="ping"),
            ]
        ).strip()
        console.print(f"[green]llama.cpp 连通 OK[/green] response={out!r}")
    except Exception as e:
        console.print(f"[red]llama.cpp 连通失败：{e}[/red]")
        raise typer.Exit(code=3)


def _try_fix_missing_tools(tools: list[str]) -> None:
    import platform
    os_name = platform.system()
    
    commands = []
    
    if os_name == "Windows":
        # 优先使用 conda (如果在环境下)，其次 choco, scoop
        has_conda = shutil.which("conda")
        if has_conda:
            pkg_list = " ".join(tools)
            commands.append(f"conda install -c conda-forge {pkg_list} -y")
        else:
            if shutil.which("choco"):
                pkg_list = " ".join(["ripgrep" if t == "ripgrep" else "universal-ctags" for t in tools])
                commands.append(f"choco install {pkg_list} -y")
            elif shutil.which("scoop"):
                pkg_list = " ".join(tools)
                commands.append(f"scoop install {pkg_list}")
    elif os_name == "Darwin": # Mac
        if shutil.which("brew"):
            pkg_list = " ".join(tools)
            commands.append(f"brew install {pkg_list}")
    elif os_name == "Linux":
        if shutil.which("apt-get"):
            pkg_list = " ".join(["ripgrep" if t == "ripgrep" else "universal-ctags" for t in tools])
            commands.append(f"sudo apt-get update && sudo apt-get install -y {pkg_list}")

    if not commands:
        console.print("[red]未能自动匹配到适合您系统的包管理器。请参考文档手动安装。[/red]")
        return

    for cmd in commands:
        if Confirm.ask(f"是否执行安装命令: [bold cyan]{cmd}[/bold cyan]?", default=True):
            try:
                subprocess.run(cmd, shell=True, check=True)
                console.print("[green]安装指令已执行完成。[/green]")
            except Exception as e:
                console.print(f"[red]执行失败: {e}[/red]")

@app.command()
def models() -> None:
    """列出 llama.cpp OpenAI 兼容接口的模型列表（GET /v1/models）。"""
    from clude_code.llm.llama_cpp_http import LlamaCppHttpClient

    cfg = CludeConfig()
    client = LlamaCppHttpClient(
        base_url=cfg.llm.base_url,
        api_mode="openai_compat",
        model=cfg.llm.model,
        temperature=0.0,
        max_tokens=8,
        timeout_s=cfg.llm.timeout_s,
    )
    ids = client.list_model_ids()
    if not ids:
        console.print("[red]未获取到模型列表。请确认 base_url 与 /v1/models 是否可用。[/red]")
        raise typer.Exit(code=2)
    console.print("[bold]models[/bold]")
    for mid in ids:
        console.print(f"- {mid}")


