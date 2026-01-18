import logging
import typer

from clude_code.config import CludeConfig
from clude_code.observability.logger import get_logger

app = typer.Typer(help="clude: a Clude Code-like local code agent CLI (Python).")

# --- 日志初始化助手 ---
# 使用统一的 CLI 日志系统
from clude_code.cli.cli_logging import get_cli_logger, get_file_logger

# --- 导入子命令 ---
from clude_code.cli.observability_cmd import observability_app

# --- 添加子命令 ---
app.add_typer(observability_app, name="observability", help="可观测性相关命令")

# --- 命令路由 ---

@app.command()
def version() -> None:
    """显示 CLI 版本。"""
    from clude_code import __version__
    typer.echo(__version__)

@app.command()
def tools(
    schema: bool = typer.Option(False, "--schema", help="输出 JSON Schema"),
    as_json: bool = typer.Option(False, "--json", help="以 JSON 格式输出"),
    all_specs: bool = typer.Option(False, "--all", help="包含内部规范项"),
    validate: bool = typer.Option(False, "--validate", help="校验工具契约（使用 ToolSpec.example_args 做运行时 schema 校验）"),
    audit: bool = typer.Option(False, "--audit", help="审计工具注册表（检查重复定义、废弃工具、版本分布）"),
) -> None:
    """列出可用工具清单。"""
    if audit:
        from clude_code.cli.info_cmds import run_tools_audit
        run_tools_audit()
        return
    from clude_code.cli.info_cmds import run_tools_list
    run_tools_list(schema, as_json, all_specs, validate)

@app.command()
def models() -> None:
    """列出可用模型列表。"""
    from clude_code.cli.info_cmds import run_models_list
    run_models_list(get_cli_logger().console)

@app.command()
def doctor(
    model: str = typer.Option("", help="指定模型 ID"),
    select_model: bool = typer.Option(False, "--select-model", help="交互式选择模型进行连通性测试"),
    fix: bool = typer.Option(False, "--fix", help="尝试自动修复缺失依赖")
) -> None:
    """执行环境诊断与连通性检查。"""
    from clude_code.cli.doctor_cmd import run_doctor
    run_doctor(fix, model, select_model, get_cli_logger().console)

@app.command()
def chat(
    prompt: str = typer.Argument("", help="可选：启动后立即执行的输入；配合 --print/-p 进入非交互模式"),
    model: str = typer.Option("", help="指定模型 ID"),
    select_model: bool = typer.Option(False, "--select-model", help="交互式选择模型"),
    debug: bool = typer.Option(False, "--debug", help="显示执行轨迹"),
    live: bool = typer.Option(False, "--live", help="启用 50 行实时刷新界面"),
    live_ui: str = typer.Option("classic", "--live-ui", help="Live UI 风格：classic|enhanced|opencode（仅在 --live 时生效）"),
    print_mode: bool = typer.Option(False, "--print", "-p", help="非交互：执行一次 prompt 后退出（对标 Claude Code -p）"),
    output_format: str = typer.Option("text", "--output-format", help="输出格式：text|json（--print 时生效）"),
    yes: bool = typer.Option(False, "--yes", help="非交互模式下自动同意需要确认的操作（有风险）"),
    cont: bool = typer.Option(False, "--continue", "-c", help="继续最近会话（对标 Claude Code -c）"),
    resume: str = typer.Option("", "--resume", "-r", help="恢复指定会话 ID（对标 Claude Code -r）"),
) -> None:
    """启动交互式 Agent 会话（或使用 --print 非交互执行）。"""
    from clude_code.cli.chat_handler import ChatHandler
    
    cfg = CludeConfig()
    if model:
        cfg.llm.model = model
    
    # 会话恢复：-c / -r
    from clude_code.cli.session_store import load_latest_session, load_session

    history = None
    session_id = None
    if resume:
        loaded = load_session(cfg.workspace_root, resume.strip())
        if loaded is None:
            raise typer.BadParameter(f"未找到会话: {resume}")
        history = loaded.history
        session_id = loaded.session_id
    elif cont:
        loaded = load_latest_session(cfg.workspace_root)
        if loaded is not None:
            history = loaded.history
            session_id = loaded.session_id

    handler = ChatHandler(cfg, session_id=session_id, history=history)
    
    if select_model:
        handler.select_model_interactively()
    
    live_ui = (live_ui or "classic").strip().lower()
    if live_ui not in {"classic", "enhanced", "opencode", "textual"}:
        raise typer.BadParameter("live_ui 必须为 classic、enhanced 或 opencode")

    if print_mode:
        if live:
            raise typer.BadParameter("--print 与 --live 不能同时使用")
        fmt = (output_format or "text").strip().lower()
        if fmt not in {"text", "json"}:
            raise typer.BadParameter("--output-format 必须为 text 或 json")
        handler.run_print(prompt, debug=debug, output_format=fmt, yes=yes)
        return

    # 交互模式：忽略 prompt（如需“先执行一次再进入 REPL”，后续可扩展）
    handler.run_loop(debug=debug, live=live, live_ui=live_ui)

if __name__ == "__main__":
    app()
