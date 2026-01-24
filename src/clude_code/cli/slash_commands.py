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

from clude_code.config.config import CludeConfig
from clude_code.cli.custom_commands import load_custom_commands
from clude_code.llm.image_utils import load_image_from_path, load_image_from_url


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
    ctx.console.print("[bold cyan]── 基础 ──[/bold cyan]")
    ctx.console.print("- `/help`：显示本帮助")
    ctx.console.print("- `/clear`：清空当前会话上下文（保留 system prompt）")
    ctx.console.print("- `/config`：显示当前配置摘要")
    ctx.console.print("[bold cyan]── 厂商/模型 ──[/bold cyan]")
    ctx.console.print("- `/providers`：列出所有可用厂商（支持 21+ 厂商）")
    ctx.console.print("- `/provider [id]`：查看或切换当前厂商")
    ctx.console.print("- `/models`：列出当前厂商的可用模型")
    ctx.console.print("- `/model [id]`：查看或切换当前模型")
    ctx.console.print("[bold cyan]── 多模态 ──[/bold cyan]")
    ctx.console.print("- `/image <path|url>`：预加载图片，下次输入时自动附加")
    ctx.console.print("- `/permissions`：查看权限与工具 allow/deny")
    ctx.console.print("- `/permissions network on|off`：开关网络权限（影响 exec 策略评估）")
    ctx.console.print("- `/permissions allow <tool...>`：设置允许工具名单（空=不限制）")
    ctx.console.print("- `/permissions deny <tool...>`：添加禁止工具名单")
    ctx.console.print("- `/permissions reset`：清空 allow/deny 列表")
    ctx.console.print("- `/tools`：列出工具（同 `clude tools`）")
    ctx.console.print("- `/doctor`：环境诊断（同 `clude doctor`）")
    ctx.console.print("- `/init`：初始化项目记忆文件 `CLUDE.md`（对标 Claude Code）")
    ctx.console.print("- `/memory`：显示 `CLUDE.md` 路径与前若干行")
    ctx.console.print("- `/bug [描述]`：生成 bug 报告文件到 `.clude/bugs/`")
    ctx.console.print("- `/cost`：显示本会话用量/成本估算（LLM 请求次数/耗时、token 估算、工具调用统计）")
    ctx.console.print("- `/commands`：列出 `.clude/commands/*.md` 自定义命令")
    ctx.console.print("- `/reload-commands`：重新加载自定义命令（无需重启）")
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
    """处理 /model 命令：查看或切换模型"""
    if not model:
        # 显示当前模型
        current = ctx.cfg.llm.model or "auto"
        if hasattr(ctx.agent, "get_current_model"):
            current = ctx.agent.get_current_model() or current
        ctx.console.print(f"[bold]当前模型[/bold]: {current}")
        ctx.console.print("[dim]用法: /model <model_id> 切换模型，/models 列出可用模型[/dim]")
        return
    
    # 使用 AgentLoop 的 switch_model 方法（如果可用）
    if hasattr(ctx.agent, "switch_model"):
        success, message = ctx.agent.switch_model(model)
        if success:
            ctx.cfg.llm.model = model  # 同步到配置
            ctx.console.print(f"[green]✓ {message}[/green]")
        else:
            ctx.console.print(f"[yellow]⚠ {message}[/yellow]")
    else:
        # 降级：直接设置（兼容旧版本）
        ctx.cfg.llm.model = model
        try:
            if hasattr(ctx.agent, "llm"):
                ctx.agent.llm.model = model
        except Exception:
            pass
        ctx.console.print(f"[green]✓ 已切换模型: {model}[/green]")


def _list_models(ctx: SlashContext) -> None:
    """处理 /models 命令：列出可用模型（增强版，显示详细信息）"""
    from rich.table import Table
    
    models_info = []
    current = ""
    current_provider = ""
    
    # 尝试从 ModelManager 获取详细信息
    try:
        from clude_code.llm import get_model_manager
        mm = get_model_manager()
        current_provider = mm.get_current_provider_id()
        current = mm.get_current_model()
        models_info = mm.list_models_info()  # 返回 ModelInfo 列表
    except Exception:
        pass
    
    # 降级：从 AgentLoop 获取
    if not models_info:
        if hasattr(ctx.agent, "list_available_models"):
            model_ids = ctx.agent.list_available_models()
            current = ctx.agent.get_current_model() if hasattr(ctx.agent, "get_current_model") else ctx.cfg.llm.model
            # 转换为简单格式
            models_info = [{"id": m, "name": m} for m in model_ids]
        elif hasattr(ctx.agent, "llm") and hasattr(ctx.agent.llm, "list_model_ids"):
            model_ids = ctx.agent.llm.list_model_ids()
            current = ctx.agent.llm.model
            models_info = [{"id": m, "name": m} for m in model_ids]
    
    if not models_info:
        ctx.console.print("[yellow]无法获取可用模型列表（API 不支持或网络错误）[/yellow]")
        ctx.console.print(f"[dim]当前配置模型: {ctx.cfg.llm.model}[/dim]")
        return
    
    # 使用 Rich Table 展示
    provider_name = current_provider or "当前厂商"
    table = Table(title=f"{provider_name} 可用模型 ({len(models_info)})")
    table.add_column("模型 ID", style="cyan")
    table.add_column("名称", style="white")
    table.add_column("上下文", justify="right")
    table.add_column("能力", justify="center")
    
    for m in models_info:
        # 处理 ModelInfo 对象或字典
        if hasattr(m, "id"):
            mid = m.id
            name = m.name
            ctx_window = f"{m.context_window // 1000}K" if m.context_window else "-"
            caps = []
            if getattr(m, "supports_vision", False):
                caps.append("🖼️")
            if getattr(m, "supports_function_call", False):
                caps.append("📞")
            if getattr(m, "supports_streaming", True):
                caps.append("🌊")
            caps_str = " ".join(caps)
        else:
            mid = m.get("id", "")
            name = m.get("name", mid)
            ctx_window = "-"
            caps_str = ""
        
        # 标记当前模型
        if mid == current:
            mid = f"★ {mid}"
            style = "green"
        else:
            style = None
        
        table.add_row(mid, name, ctx_window, caps_str, style=style)
    
    ctx.console.print(table)
    ctx.console.print("")
    ctx.console.print("[dim]🖼️ = Vision  📞 = Function Call  🌊 = Streaming  ★ = 当前使用[/dim]")
    ctx.console.print(f"[dim]用 /model <id> 切换模型，/providers 查看厂商[/dim]")


def _list_providers(ctx: SlashContext) -> None:
    """处理 /providers 命令：列出所有可用厂商"""
    from rich.table import Table
    
    providers = []
    current_provider = ""
    
    # 获取当前厂商 ID
    try:
        from clude_code.llm import get_model_manager
        mm = get_model_manager()
        current_provider = mm.get_current_provider_id()
    except Exception:
        pass
    
    # 从 ProviderRegistry 获取所有可用厂商（而不是 ModelManager 中已注册的）
    try:
        from clude_code.llm.registry import ProviderRegistry
        providers = ProviderRegistry.list_providers()
    except Exception as e:
        ctx.console.print(f"[red]获取厂商列表失败: {e}[/red]")
        return
    
    if not providers:
        ctx.console.print("[yellow]未找到已注册的厂商[/yellow]")
        return
    
    # 使用 Rich Table 展示
    table = Table(title=f"可用模型厂商 ({len(providers)})")
    table.add_column("#", style="dim", width=3)
    table.add_column("厂商 ID", style="cyan")
    table.add_column("名称", style="white")
    table.add_column("类型", style="yellow")
    table.add_column("区域", style="magenta")
    
    for i, p in enumerate(providers, 1):
        pid = p.get("id", "")
        name = p.get("name", pid)
        ptype = p.get("type", "-")
        region = p.get("region", "-")
        
        # 标记当前厂商
        is_current = pid == current_provider
        if is_current:
            pid = f"★ {pid}"
            style = "green"
        else:
            style = None
        
        table.add_row(str(i), pid, name, ptype, region, style=style)
    
    ctx.console.print(table)
    ctx.console.print("")
    ctx.console.print("[dim]★ = 当前使用[/dim]")
    ctx.console.print("[dim]用 /provider <id> 切换厂商，/models 查看模型[/dim]")


def _switch_provider(ctx: SlashContext, provider_id: str | None) -> None:
    """处理 /provider <name> 命令：切换厂商"""
    if not provider_id:
        # 显示当前厂商
        current = ""
        try:
            from clude_code.llm import get_model_manager
            mm = get_model_manager()
            current = mm.get_current_provider_id()
        except Exception:
            pass
        
        ctx.console.print(f"[bold]当前厂商[/bold]: {current or '未设置'}")
        ctx.console.print("[dim]用法: /provider <provider_id> 切换厂商，/providers 列出所有厂商[/dim]")
        return
    
    # 切换厂商
    try:
        from clude_code.llm import get_model_manager, ProviderRegistry, ProviderConfig
        mm = get_model_manager()
        
        # 检查厂商是否已注册到 ModelManager
        if provider_id not in [p.get("id") for p in mm.list_providers()]:
            # 尝试从 Registry 获取并注册
            if ProviderRegistry.has_provider(provider_id):
                # 从配置获取厂商配置
                provider_cfg_item = getattr(ctx.cfg.providers, provider_id, None)
                if provider_cfg_item:
                    config = ProviderConfig(
                        name=provider_id,
                        api_key=provider_cfg_item.api_key,
                        base_url=provider_cfg_item.base_url,
                        api_version=provider_cfg_item.api_version,
                        default_model=provider_cfg_item.default_model,
                        timeout_s=provider_cfg_item.timeout_s,
                        extra=provider_cfg_item.extra,
                    )
                else:
                    config = ProviderConfig(name=provider_id)
                
                provider = ProviderRegistry.get_provider(provider_id, config)
                mm.register_provider(provider_id, provider)
            else:
                # 列出可用厂商
                from clude_code.llm import list_providers
                available = [p.get("id") for p in list_providers()]
                ctx.console.print(f"[red]✗ 未知厂商: {provider_id}[/red]")
                ctx.console.print(f"[dim]可用厂商: {', '.join(available[:10])}...[/dim]")
                return
        
        # 执行切换
        success, message = mm.switch_provider(provider_id)
        if success:
            ctx.console.print(f"[green]✓ {message}[/green]")
            # 显示当前模型
            current_model = mm.get_current_model()
            if current_model:
                ctx.console.print(f"[dim]当前模型: {current_model}[/dim]")
            # 显示可用模型数
            models = mm.list_models()
            ctx.console.print(f"[dim]可用模型: {len(models)} 个[/dim]")
        else:
            ctx.console.print(f"[yellow]⚠ {message}[/yellow]")
    except Exception as e:
        ctx.console.print(f"[red]✗ 切换厂商失败: {e}[/red]")


def _load_image(ctx: SlashContext, path_or_url: str | None) -> bool:
    """
    处理 /image 命令：预加载图片。
    
    图片会被缓存到 ChatHandler._pending_images，下次用户输入时自动附加。
    
    Returns:
        True 如果成功加载
    """
    if not path_or_url:
        ctx.console.print("[yellow]用法: /image <path|url>[/yellow]")
        ctx.console.print("[dim]示例: /image screenshot.png[/dim]")
        ctx.console.print("[dim]示例: /image https://example.com/image.png[/dim]")
        return False
    
    # 加载图片
    if path_or_url.startswith(('http://', 'https://')):
        img = load_image_from_url(path_or_url)
    else:
        img = load_image_from_path(path_or_url)
    
    if not img:
        ctx.console.print(f"[red]✗ 无法加载图片: {path_or_url}[/red]")
        return False
    
    # 存储到 agent（通过回调或属性）
    # 注意：这里需要访问 ChatHandler 的 _pending_images/_pending_image_paths
    # 由于 SlashContext 只有 agent，我们通过 agent 的属性来传递
    if not hasattr(ctx.agent, "_pending_images"):
        ctx.agent._pending_images = []
    ctx.agent._pending_images.append(img)
    if not hasattr(ctx.agent, "_pending_image_paths"):
        ctx.agent._pending_image_paths = []
    ctx.agent._pending_image_paths.append(path_or_url)
    
    ctx.console.print(f"[green]✓ 图片已预加载: {path_or_url}[/green]")
    ctx.console.print("[dim]下次输入时将自动附加此图片[/dim]")
    return True


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
    对标 Claude Code 的 /init：初始化项目记忆文件（CLUDE.md）。
    """
    root = Path(ctx.cfg.workspace_root)
    p = root / "CLUDE.md"
    if p.exists():
        ctx.console.print(f"[yellow]已存在[/yellow]: {p}")
        return

    template = (
        "# CLUDE.md（项目记忆 / 协作规则）\n\n"
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
    p = root / "CLUDE.md"
    ctx.console.print(f"[bold]记忆文件[/bold]: {p}")
    if not p.exists():
        ctx.console.print("[yellow]未找到 CLUDE.md，可用 /init 生成[/yellow]")
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
    try:
        sid = getattr(ctx.agent, "session_id", None)
        if sid:
            body.append(f"- session_id: {sid}\n")
    except Exception:
        pass
    if ctx.last_trace_id:
        body.append(f"- last_trace_id: {ctx.last_trace_id}\n")

    # 用量摘要（如果可用）
    try:
        usage = getattr(ctx.agent, "usage", None)
        if usage is not None:
            s = usage.summary()
            body.append("\n## 用量/成本（估算）\n")
            body.append(f"- llm_requests: {s.get('llm_requests')}\n")
            body.append(f"- llm_total_ms: {s.get('llm_total_ms')}\n")
            body.append(f"- prompt_tokens_est: {s.get('prompt_tokens_est')}\n")
            body.append(f"- completion_tokens_est: {s.get('completion_tokens_est')}\n")
            body.append(f"- total_tokens_est: {s.get('total_tokens_est')}\n")
            body.append(f"- tool_calls: {s.get('tool_calls')}\n")
            body.append(f"- tool_failures: {s.get('tool_failures')}\n")
    except Exception:
        pass
    body.append("\n## 附件（建议）\n")
    body.append("- `.clude/logs/trace.jsonl`（筛选 trace_id）\n")
    body.append("- `.clude/logs/audit.jsonl`（筛选 trace_id）\n")
    body.append("\n")

    p.write_text("".join(body), encoding="utf-8")
    ctx.console.print(f"[green]✓ 已生成 bug 报告[/green]: {p}")

def _cost(ctx: SlashContext) -> None:
    usage = getattr(ctx.agent, "usage", None)
    if usage is None:
        ctx.console.print("[yellow]当前会话未启用用量统计（usage 未初始化）[/yellow]")
        return
    s = usage.summary()
    ctx.console.print("[bold]本会话用量/成本（估算）[/bold]")
    ctx.console.print(f"- llm_requests: {s.get('llm_requests')}")
    ctx.console.print(f"- llm_total_ms: {s.get('llm_total_ms')}")
    ctx.console.print(f"- prompt_tokens_est: {s.get('prompt_tokens_est')}")
    ctx.console.print(f"- completion_tokens_est: {s.get('completion_tokens_est')}")
    ctx.console.print(f"- total_tokens_est: {s.get('total_tokens_est')}")
    ctx.console.print(f"- tool_calls: {s.get('tool_calls')} (failures={s.get('tool_failures')})")
    ctx.console.print("")

def _commands(ctx: SlashContext) -> None:
    cmds = load_custom_commands(ctx.cfg.workspace_root)
    if not cmds:
        ctx.console.print("[yellow]未发现自定义命令：.clude/commands/*.md[/yellow]")
        return
    ctx.console.print("[bold]自定义命令（.clude/commands/*.md）[/bold]")
    for c in cmds:
        meta = c.meta or {}
        args = meta.get("args") or []
        req = meta.get("required") or []
        tips = []
        if args:
            tips.append(f"args={args}")
        if req:
            tips.append(f"required={req}")
        if meta.get("allowed_tools"):
            tips.append("allowed_tools=...")
        if meta.get("disallowed_tools"):
            tips.append("disallowed_tools=...")
        if "allow_network" in meta:
            tips.append(f"allow_network={meta.get('allow_network')}")
        tip_str = ("  [dim]" + " ".join(tips) + "[/dim]") if tips else ""
        ctx.console.print(f"- `/{c.name}`: {c.description}  [dim]({Path(c.path).name})[/dim]{tip_str}")
    ctx.console.print("")


def _reload_commands(ctx: SlashContext) -> None:
    # 目前自定义命令缓存放在 ChatHandler；此处提供“可见的 reload”提示
    # 实际刷新由 ChatHandler 的下一轮输入重新加载（或用户重启）
    # 为了保持最小侵入，这里仅做 UX 提示。
    ctx.console.print("[green]✓ 已提示重新加载命令[/green]：请在当前会话中输入任意内容触发 reload（或重启 clude chat）")


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
    if cmd == "/models":
        _list_models(ctx)
        return True
    if cmd == "/providers":
        _list_providers(ctx)
        return True
    if cmd == "/provider":
        _switch_provider(ctx, args[0] if args else None)
        return True
    if cmd == "/image":
        _load_image(ctx, args[0] if args else None)
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
    if cmd == "/cost":
        _cost(ctx)
        return True
    if cmd == "/commands":
        _commands(ctx)
        return True
    if cmd in {"/reload-commands", "/reload_commands"}:
        _reload_commands(ctx)
        return True

    # 兼容：退出命令（Claude Code 常见：/quit /exit）
    if cmd in {"/quit", "/exit"}:
        ctx.console.print("[bold yellow]再见！[/bold yellow]")
        raise SystemExit(0)

    ctx.console.print("[red]未知命令。用 /help 查看可用命令[/red]")
    return True


