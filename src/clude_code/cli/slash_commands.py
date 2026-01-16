"""
Claude Code 风格的 Slash Commands（交互会话内 `/xxx` 命令）。

业界对标：
- Anthropic Claude Code 在终端 REPL 中提供 `/help`、`/bug`、`/config`、`/model`、`/permissions` 等命令，
  用于本地控制会话、配置与权限（见官方仓库与文档）。

本项目目标：
- 在不走 LLM 的情况下，为 clude chat 提供稳定、可扩展的“本地命令层”
- 命令必须无副作用或明确提示副作用，并写入必要的审计/日志（后续可扩展）
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from rich.console import Console

from clude_code.config import CludeConfig


@dataclass
class SlashContext:
    console: Console
    cfg: CludeConfig
    agent: Any  # AgentLoop（避免在 CLI 层引入重型类型依赖）
    debug: bool

    # 可选：用于 /bug 关联
    last_trace_id: str | None = None
    last_user_text: str | None = None


def _print_help(ctx: SlashContext) -> None:
    ctx.console.print("[bold]可用命令（Slash Commands）[/bold]")
    ctx.console.print("- `/help`：显示本帮助")
    ctx.console.print("- `/clear`：清空当前会话上下文（保留 system prompt）")
    ctx.console.print("- `/config`：显示当前配置摘要")
    ctx.console.print("- `/model [id]`：查看或切换当前模型（本会话生效）")
    ctx.console.print("- `/permissions`：查看权限与工具 allow/deny")
    ctx.console.print("- `/permissions network on|off`：开关网络权限（影响 exec 策略评估）")
    ctx.console.print("- `/permissions allow <tool...>`：设置允许工具名单（空=不限制）")
    ctx.console.print("- `/permissions deny <tool...>`：添加禁止工具名单")
    ctx.console.print("- `/permissions reset`：清空 allow/deny 列表")
    ctx.console.print("- `/tools`：列出工具（同 `clude tools`）")
    ctx.console.print("- `/doctor`：环境诊断（同 `clude doctor`）")
    ctx.console.print("- `/init`：初始化项目记忆文件 `CLAUDE.md`（对标 Claude Code）")
    ctx.console.print("- `/memory`：显示 `CLAUDE.md` 路径与前若干行")
    ctx.console.print("- `/bug [描述]`：生成 bug 报告文件到 `.clude/bugs/`")
    ctx.console.print("")


def _do_clear(ctx: SlashContext) -> None:
    # Claude Code /clear：清空会话历史（保留 system）
    try:
        msgs = getattr(ctx.agent, "messages", None)
        if isinstance(msgs, list) and msgs:
            ctx.agent.messages = [msgs[0]]
        ctx.console.print("[green]✓ 已清空会话上下文（保留 system prompt）[/green]")
    except Exception as e:
        ctx.console.print(f"[red]✗ 清空失败: {e}[/red]")


def _show_config(ctx: SlashContext) -> None:
    c = ctx.cfg
    ctx.console.print("[bold]当前配置（摘要）[/bold]")
    ctx.console.print(f"- workspace_root: {c.workspace_root}")
    ctx.console.print(f"- llm.base_url: {c.llm.base_url}")
    ctx.console.print(f"- llm.api_mode: {c.llm.api_mode}")
    ctx.console.print(f"- llm.model: {c.llm.model}")
    ctx.console.print(f"- policy.allow_network: {c.policy.allow_network}")
    ctx.console.print(f"- policy.confirm_write: {c.policy.confirm_write}")
    ctx.console.print(f"- policy.confirm_exec: {c.policy.confirm_exec}")
    # 可选字段（P0-P1 演进）
    allowed = getattr(c.policy, "allowed_tools", [])
    denied = getattr(c.policy, "disallowed_tools", [])
    ctx.console.print(f"- policy.allowed_tools: {allowed}")
    ctx.console.print(f"- policy.disallowed_tools: {denied}")
    ctx.console.print("")


def _set_model(ctx: SlashContext, model: str | None) -> None:
    if not model:
        ctx.console.print(f"[bold]当前模型[/bold]: {ctx.cfg.llm.model or 'auto'}")
        return
    ctx.cfg.llm.model = model
    # 同步到运行中的 LLM client（本会话即时生效）
    try:
        if hasattr(ctx.agent, "llm"):
            ctx.agent.llm.model = model
    except Exception:
        pass
    ctx.console.print(f"[green]✓ 已切换模型: {model}[/green]")


def _permissions(ctx: SlashContext, args: list[str]) -> None:
    p = ctx.cfg.policy
    allowed: list[str] = list(getattr(p, "allowed_tools", []) or [])
    denied: list[str] = list(getattr(p, "disallowed_tools", []) or [])

    if not args:
        ctx.console.print("[bold]权限状态[/bold]")
        ctx.console.print(f"- allow_network: {p.allow_network}")
        ctx.console.print(f"- confirm_write: {p.confirm_write}")
        ctx.console.print(f"- confirm_exec: {p.confirm_exec}")
        ctx.console.print(f"- allowed_tools: {allowed}  （空=不限制）")
        ctx.console.print(f"- disallowed_tools: {denied}")
        ctx.console.print("")
        return

    sub = args[0].lower()
    if sub == "network" and len(args) >= 2:
        v = args[1].lower()
        if v in {"on", "true", "1", "yes"}:
            p.allow_network = True
        elif v in {"off", "false", "0", "no"}:
            p.allow_network = False
        else:
            ctx.console.print("[red]用法: /permissions network on|off[/red]")
            return
        ctx.console.print(f"[green]✓ allow_network={p.allow_network}[/green]")
        return

    if sub == "allow":
        new = [x for x in args[1:] if x]
        p.allowed_tools = new
        ctx.console.print(f"[green]✓ 已设置 allowed_tools={new}[/green]")
        return

    if sub in {"deny", "disallow"}:
        add = [x for x in args[1:] if x]
        merged = sorted(set(denied + add))
        p.disallowed_tools = merged
        ctx.console.print(f"[green]✓ 已更新 disallowed_tools={merged}[/green]")
        return

    if sub in {"reset", "clear"}:
        p.allowed_tools = []
        p.disallowed_tools = []
        ctx.console.print("[green]✓ 已清空 allow/deny 工具列表[/green]")
        return

    ctx.console.print("[red]未知 permissions 子命令。用 /permissions 查看用法[/red]")


def _tools(ctx: SlashContext) -> None:
    from clude_code.cli.info_cmds import run_tools_list

    run_tools_list(schema=False, as_json=False, all_specs=False, validate=False)


def _doctor(ctx: SlashContext) -> None:
    from clude_code.cli.doctor_cmd import run_doctor
    from clude_code.cli.cli_logging import get_cli_logger

    # 默认只诊断，不自动修复；模型使用当前 cfg
    run_doctor(fix=False, model=ctx.cfg.llm.model or "", select_model=False, logger=get_cli_logger().console)


def _init_memory(ctx: SlashContext) -> None:
    """
    对标 Claude Code 的 /init：初始化项目记忆文件（CLAUDE.md）。
    """
    root = Path(ctx.cfg.workspace_root)
    p = root / "CLAUDE.md"
    if p.exists():
        ctx.console.print(f"[yellow]已存在[/yellow]: {p}")
        return

    template = (
        "# CLAUDE.md（项目记忆 / 协作规则）\n\n"
        "本文件用于给 Code Agent 提供仓库级别的长期规则与背景信息。\n\n"
        "## 项目目标\n"
        "- （在这里写：项目做什么、不做什么）\n\n"
        "## 代码规范\n"
        "- 参见 `docs/CODE_SPECIFICATION.md`\n\n"
        "## 安全与权限\n"
        "- 默认禁止网络；写文件/执行命令需要确认\n\n"
        "## 常见命令\n"
        "- `clude doctor` 环境诊断\n"
        "- `clude tools --validate` 工具契约自检\n\n"
    )
    p.write_text(template, encoding="utf-8")
    ctx.console.print(f"[green]✓ 已生成[/green]: {p}")


def _memory(ctx: SlashContext) -> None:
    root = Path(ctx.cfg.workspace_root)
    p = root / "CLAUDE.md"
    ctx.console.print(f"[bold]记忆文件[/bold]: {p}")
    if not p.exists():
        ctx.console.print("[yellow]未找到 CLAUDE.md，可用 /init 生成[/yellow]")
        return
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        preview = "\n".join(lines[:40])
        ctx.console.print("[dim]--- preview (first 40 lines) ---[/dim]")
        ctx.console.print(preview)
    except Exception as e:
        ctx.console.print(f"[red]读取失败: {e}[/red]")


def _bug(ctx: SlashContext, desc: str | None) -> None:
    root = Path(ctx.cfg.workspace_root)
    out_dir = root / ".clude" / "bugs"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    p = out_dir / f"bug_{ts}.md"

    try:
        from clude_code import __version__
    except Exception:
        __version__ = "unknown"

    body = []
    body.append("# Bug Report\n")
    body.append("## 描述\n")
    body.append((desc or "（请补充复现步骤与期望/实际行为）") + "\n")
    body.append("## 环境\n")
    body.append(f"- clude-code: {__version__}\n")
    body.append(f"- workspace_root: {ctx.cfg.workspace_root}\n")
    body.append(f"- model: {ctx.cfg.llm.model}\n")
    body.append(f"- base_url: {ctx.cfg.llm.base_url}\n")
    if ctx.last_trace_id:
        body.append(f"- last_trace_id: {ctx.last_trace_id}\n")
    body.append("\n## 附件（建议）\n")
    body.append("- `.clude/logs/trace.jsonl`（筛选 trace_id）\n")
    body.append("- `.clude/logs/audit.jsonl`（筛选 trace_id）\n")
    body.append("\n")

    p.write_text("".join(body), encoding="utf-8")
    ctx.console.print(f"[green]✓ 已生成 bug 报告[/green]: {p}")


def handle_slash_command(ctx: SlashContext, text: str) -> bool:
    """
    处理一条 `/xxx` 命令。
    返回 True 表示“已处理（不再进入 LLM/Agent）”。
    """
    raw = (text or "").strip()
    if not raw.startswith("/"):
        return False

    parts = raw.split()
    cmd = parts[0].lower()
    args = parts[1:]

    if cmd in {"/help", "/?"}:
        _print_help(ctx)
        return True
    if cmd == "/clear":
        _do_clear(ctx)
        return True
    if cmd == "/config":
        _show_config(ctx)
        return True
    if cmd == "/model":
        _set_model(ctx, args[0] if args else None)
        return True
    if cmd == "/permissions":
        _permissions(ctx, args)
        return True
    if cmd == "/tools":
        _tools(ctx)
        return True
    if cmd == "/doctor":
        _doctor(ctx)
        return True
    if cmd == "/init":
        _init_memory(ctx)
        return True
    if cmd == "/memory":
        _memory(ctx)
        return True
    if cmd == "/bug":
        _bug(ctx, " ".join(args) if args else None)
        return True

    # 兼容：退出命令（Claude Code 常见：/quit /exit）
    if cmd in {"/quit", "/exit"}:
        ctx.console.print("[bold yellow]再见！[/bold yellow]")
        raise SystemExit(0)

    ctx.console.print("[red]未知命令。用 /help 查看可用命令[/red]")
    return True


