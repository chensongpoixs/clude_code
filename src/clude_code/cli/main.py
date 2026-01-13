import logging
import typer

from clude_code.config import CludeConfig
from clude_code.observability.logger import get_logger

app = typer.Typer(help="clude: a Claude Code-like local code agent CLI (Python).")

# --- 日志初始化助手 ---

_logger_instance = None
def get_cli_logger() -> logging.Logger:
    global _logger_instance
    if _logger_instance is None:
        cfg = CludeConfig()
        _logger_instance = get_logger(
            __name__,
            workspace_root=cfg.workspace_root,
            log_to_console=cfg.logging.log_to_console,
        )
    return _logger_instance

_file_only_logger_instance = None
def get_file_only_logger() -> logging.Logger:
    global _file_only_logger_instance
    if _file_only_logger_instance is None:
        cfg = CludeConfig()
        _file_only_logger_instance = get_logger(
            f"{__name__}.flow",
            workspace_root=cfg.workspace_root,
            log_to_console=False,
        )
    return _file_only_logger_instance

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
) -> None:
    """列出可用工具清单。"""
    from clude_code.cli.info_cmds import run_tools_list
    run_tools_list(schema, as_json, all_specs)

@app.command()
def models() -> None:
    """列出可用模型列表。"""
    from clude_code.cli.info_cmds import run_models_list
    run_models_list(get_cli_logger())

@app.command()
def doctor(
    fix: bool = typer.Option(False, "--fix", help="尝试自动修复缺失依赖")
) -> None:
    """执行环境诊断与连通性检查。"""
    from clude_code.cli.doctor_cmd import run_doctor
    run_doctor(fix, get_cli_logger())

@app.command()
def chat(
    model: str = typer.Option("", help="指定模型 ID"),
    select_model: bool = typer.Option(False, "--select-model", help="交互式选择模型"),
    debug: bool = typer.Option(False, "--debug", help="显示执行轨迹"),
    live: bool = typer.Option(False, "--live", help="启用 50 行实时刷新界面"),
) -> None:
    """启动交互式 Agent 会话。"""
    from clude_code.cli.chat_handler import ChatHandler
    
    cfg = CludeConfig()
    if model:
        cfg.llm.model = model
    
    handler = ChatHandler(cfg, get_cli_logger(), get_file_only_logger())
    
    if select_model:
        handler.select_model_interactively()
    
    handler.run_loop(debug=debug, live=live)

if __name__ == "__main__":
    app()
