from pathlib import Path

import typer
from rich.console import Console
from rich.prompt import Confirm
from rich.prompt import Prompt

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

    while True:
        user_text = typer.prompt("you")
        if user_text.strip().lower() in {"exit", "quit"}:
            console.print("bye")
            return
        turn = agent.run_turn(user_text, confirm=_confirm)
        console.print("\n[bold]assistant[/bold]")
        console.print(turn.assistant_text)
        console.print("")


@app.command()
def doctor() -> None:
    """Basic diagnostics: workspace + llama.cpp connectivity."""
    from clude_code.llm.llama_cpp_http import ChatMessage, LlamaCppHttpClient

    cfg = CludeConfig()
    console.print("[bold]clude doctor[/bold]")
    console.print(f"- workspace_root: {cfg.workspace_root}")
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


