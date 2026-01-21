import shutil
import subprocess
import platform
from pathlib import Path
import logging

import typer
from rich.console import Console
from rich.prompt import Confirm

from clude_code.config.config import CludeConfig
from clude_code.llm.llama_cpp_http import ChatMessage, LlamaCppHttpClient
from clude_code.orchestrator.agent_loop.tool_dispatch import iter_tool_specs
from clude_code.cli.utils import select_model_interactively

console = Console()

def run_doctor(fix: bool, model: str, select_model: bool, logger: logging.Logger) -> None:
    """执行环境诊断。"""
    cfg = CludeConfig()
    if model:
        cfg.llm.model = model
    
    if select_model:
        select_model_interactively(cfg, logger)

    logger.info("[bold]clude doctor[/bold]")
    
    missing_tools = []

    # 1) 从 ToolSpec 推导外部依赖
    required_bins: dict[str, set[str]] = {}
    optional_bins: dict[str, set[str]] = {}
    for s in iter_tool_specs():
        for b in s.external_bins_required:
            required_bins.setdefault(b, set()).add(s.name)
        for b in s.external_bins_optional:
            optional_bins.setdefault(b, set()).add(s.name)

    def _bin_status(bin_name: str) -> str:
        return shutil.which(bin_name) or "[red]NOT FOUND[/red]"

    # 必需依赖
    if required_bins:
        logger.info("\n[bold]外部依赖（必需）[/bold]")
        for b, owners in sorted(required_bins.items(), key=lambda x: x[0]):
            logger.info(f"- {b}: {_bin_status(b)}  影响: {', '.join(sorted(owners))}")
            if not shutil.which(b):
                missing_tools.append("ripgrep" if b == "rg" else ("universal-ctags" if b == "ctags" else b))

    # 推荐依赖
    if optional_bins:
        logger.info("\n[bold]外部依赖（推荐）[/bold]")
        for b, owners in sorted(optional_bins.items(), key=lambda x: x[0]):
            owners_disp = [o[1:] if o.startswith("_") else o for o in sorted(owners)]
            logger.info(f"- {b}: {_bin_status(b)}  影响: {', '.join(owners_disp)}")
            if not shutil.which(b):
                missing_tools.append("ripgrep" if b == "rg" else ("universal-ctags" if b == "ctags" else b))

    if missing_tools and fix:
        logger.warning(f"\n[bold yellow]检测到缺失工具: {', '.join(missing_tools)}[/bold yellow]")
        _try_fix_missing_tools(missing_tools, logger)
        return run_doctor(fix=False, model="", select_model=False, logger=logger)

    if missing_tools and not fix:
        logger.warning("\n提示: 使用 `clude doctor --fix` 可尝试自动修复缺失工具。")

    logger.info(f"\n- workspace_root: {cfg.workspace_root}")
    logger.info(f"- llama base_url: {cfg.llm.base_url}")

    # 2) 检查工作区读写
    wr = Path(cfg.workspace_root)
    if not wr.exists():
        logger.error("workspace_root 不存在")
        raise typer.Exit(code=2)
    try:
        p = wr / ".clude" / "doctor.tmp"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("ok", encoding="utf-8")
        p.unlink(missing_ok=True)
        logger.info("[green]workspace 可读写 OK[/green]")
    except Exception as e:
        logger.error(f"workspace 写入失败: {e}", exc_info=True)
        raise typer.Exit(code=2)

    # 3) 检查 LLM 服务连通性（支持 OpenAI / llama.cpp / Ollama 等）
    try:
        client = LlamaCppHttpClient(
            base_url=cfg.llm.base_url,
            api_mode=cfg.llm.api_mode,
            model=cfg.llm.model,
            temperature=0.0,
            max_tokens=32,
            timeout_s=cfg.llm.timeout_s,
            api_key=cfg.llm.api_key,  # 支持 OpenAI 等需要认证的 API
        )
        out = client.chat([
            ChatMessage(role="system", content="你是诊断助手，只输出 OK。"),
            ChatMessage(role="user", content="ping"),
        ]).strip()
        provider = cfg.llm.provider or "openai_compat"
        logger.info(f"[green]LLM 服务连通 OK ({provider})[/green] response={out!r}")
    except Exception as e:
        logger.error(f"llama.cpp 连通失败: {e}", exc_info=True)
        raise typer.Exit(code=3)

def _try_fix_missing_tools(tools: list[str], logger: logging.Logger) -> None:
    os_name = platform.system()
    commands = []
    
    if os_name == "Windows":
        if shutil.which("conda"):
            pkg_list = " ".join(tools)
            commands.append(f"conda install -c conda-forge {pkg_list} -y")
        else:
            if shutil.which("choco"):
                pkg_list = " ".join(["ripgrep" if t == "ripgrep" else "universal-ctags" for t in tools])
                commands.append(f"choco install {pkg_list} -y")
            elif shutil.which("scoop"):
                commands.append(f"scoop install {' '.join(tools)}")
    elif os_name == "Darwin" and shutil.which("brew"):
        commands.append(f"brew install {' '.join(tools)}")
    elif os_name == "Linux" and shutil.which("apt-get"):
        pkg_list = " ".join(["ripgrep" if t == "ripgrep" else "universal-ctags" for t in tools])
        commands.append(f"sudo apt-get update && sudo apt-get install -y {pkg_list}")

    if not commands:
        logger.error("未能自动匹配到适合您系统的包管理器。请参考文档手动安装。")
        return

    for cmd in commands:
        if Confirm.ask(f"是否执行安装命令: [bold cyan]{cmd}[/bold cyan]?", default=True):
            try:
                subprocess.run(cmd, shell=True, check=True)
                logger.info("[green]安装指令已执行完成。[/green]")
            except Exception as e:
                logger.error(f"安装指令执行失败: {e}", exc_info=True)

