import json
import logging
from rich.console import Console
from rich.table import Table
import typer

from clude_code.orchestrator.agent_loop.tool_dispatch import iter_tool_specs
from clude_code.llm.llama_cpp_http import LlamaCppHttpClient
from clude_code.config import CludeConfig

console = Console()

def _validate_tool_specs(specs) -> tuple[bool, list[dict[str, str]]]:
    """
    校验 ToolSpec 契约一致性（MVP 版）：
    - 使用 ToolSpec.example_args 执行 validate_args（Pydantic 运行时强校验）
    - 仅做“契约层”校验，不执行工具（避免 write/exec 副作用）
    返回: (ok, failures)
    """
    failures: list[dict[str, str]] = []
    for s in specs:
        try:
            ok, msg_or_args = s.validate_args(s.example_args or {})
            if not ok:
                failures.append(
                    {
                        "tool": s.name,
                        "error": str(msg_or_args),
                    }
                )
        except Exception as e:
            failures.append({"tool": s.name, "error": f"校验异常: {type(e).__name__}: {e}"})
    return (len(failures) == 0), failures


def run_tools_list(schema: bool, as_json: bool, all_specs: bool, validate: bool = False) -> None:
    """列出可用工具清单。"""
    # 使用新的工具注册表
    from clude_code.orchestrator.agent_loop.tool_dispatch import get_tool_registry
    registry = get_tool_registry()

    specs = registry.list_tools(callable_only=not all_specs, include_deprecated=False)

    if validate:
        ok, failures = _validate_tool_specs(specs)
        if ok:
            console.print("[green]✓ 工具契约校验通过：所有工具的 example_args 均可通过运行时 schema 校验[/green]")
            return
        console.print(f"[red]✗ 工具契约校验失败：{len(failures)} 个工具不通过[/red]")
        table = Table(show_header=True, box=None)
        table.add_column("工具名", style="bold cyan", width=20)
        table.add_column("错误", style="red")
        for f in failures[:50]:
            table.add_row(f["tool"], f["error"])
        console.print(table)
        raise typer.Exit(code=2)

    if as_json:
        payload = []
        for s in specs:
            obj = {
                "name": s.name,
                "summary": s.summary,
                "description": s.description,
                "category": s.category,
                "priority": s.priority,
                "side_effects": sorted(s.side_effects),
                "example_args": s.example_args,
                "cacheable": s.cacheable,
                "timeout_seconds": s.timeout_seconds,
                "requires_confirmation": s.requires_confirmation,
                "version": s.version,
            }
            if schema:
                obj["args_schema"] = s.args_schema
            payload.append(obj)
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    # 按分类分组显示
    categories = registry.get_categories()

    for category, count in categories.items():
        console.print(f"\n[bold blue]{category.upper()}[/bold blue] 工具 ({count}个)")

        category_tools = registry.list_tools(category=category, callable_only=not all_specs)
        if not category_tools:
            continue

        table = Table(show_header=True, box=None)
        table.add_column("工具名", style="bold cyan", width=15)
        table.add_column("优先级", style="yellow", width=6, justify="center")
        table.add_column("副作用", style="magenta", width=12)
        table.add_column("描述", style="white")
        if schema:
            table.add_column("参数模式", style="dim", width=20)

        for s in category_tools:
            priority_icon = "⭐" * min(s.priority + 1, 3) if s.priority > 0 else "○"
            se = ",".join(sorted(s.side_effects)) if s.side_effects else "-"
            desc = s.description or s.summary

            row = [s.name, priority_icon, se, desc[:50] + "..." if len(desc) > 50 else desc]
            if schema:
                schema_preview = str(s.args_schema.get('type', 'object')) + \
                               f" ({len(s.args_schema.get('properties', {}))}参数)"
                row.append(schema_preview)

            table.add_row(*row)

        console.print(table)

    # 显示统计信息
    total_tools = len(specs)
    console.print(f"\n[dim]共 {total_tools} 个工具 | 按优先级和分类组织[/dim]")

def run_models_list(logger: logging.Logger) -> None:
    """列出 llama.cpp 的模型列表。"""
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
        logger.error("未获取到模型列表。")
        raise typer.Exit(code=2)
    logger.info("[bold]可用模型列表[/bold]")
    for mid in ids:
        logger.info(f"- {mid}")

