import json
import logging
from rich.console import Console
from rich.table import Table
import typer

from clude_code.orchestrator.agent_loop.tool_dispatch import iter_tool_specs
from clude_code.llm.llama_cpp_http import LlamaCppHttpClient
from clude_code.config import CludeConfig

console = Console()

def run_tools_list(schema: bool, as_json: bool, all_specs: bool) -> None:
    """列出可用工具清单。"""
    specs = [s for s in iter_tool_specs() if (all_specs or s.callable_by_model)]
    if as_json:
        payload = []
        for s in specs:
            obj = {
                "name": s.name,
                "summary": s.summary,
                "side_effects": sorted(s.side_effects),
                "example_args": s.example_args,
            }
            if schema:
                obj["args_schema"] = s.args_schema
            payload.append(obj)
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    table = Table(title="clude 可用工具（ToolSpec 注册表）")
    table.add_column("name", style="bold cyan")
    table.add_column("side_effects", style="magenta")
    table.add_column("summary", style="white")
    if schema:
        table.add_column("args_schema", style="dim")

    for s in specs:
        se = ",".join(sorted(s.side_effects)) if s.side_effects else "-"
        row = [s.name, se, s.summary]
        if schema:
            row.append(json.dumps(s.args_schema, ensure_ascii=False))
        table.add_row(*row)
    console.print(table)

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

