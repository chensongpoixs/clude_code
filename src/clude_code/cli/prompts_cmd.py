"""
Prompt 版本管理 CLI

命令：
- clude prompts list: 列出所有 prompt 文件
- clude prompts versions <path>: 列出指定 prompt 的所有版本
- clude prompts show <path>: 显示 prompt 内容
- clude prompts validate: 验证 prompt 目录结构
"""

import typer
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.syntax import Syntax
from rich.panel import Panel

from clude_code.prompts import (
    read_prompt,
    load_prompt_asset,
    list_prompt_versions,
    PromptAsset,
)

prompts_app = typer.Typer(help="Prompt 版本管理命令")
console = Console()

# Prompt 根目录
_PROMPTS_ROOT = Path(__file__).parent.parent / "prompts"


@prompts_app.command("list")
def list_prompts(
    directory: str = typer.Option("", "--dir", "-d", help="指定子目录（如 system/role）"),
    show_metadata: bool = typer.Option(False, "--metadata", "-m", help="显示元数据"),
) -> None:
    """列出所有 prompt 文件。"""
    root = _PROMPTS_ROOT
    if directory:
        root = root / directory
    
    if not root.exists():
        console.print(f"[red]目录不存在: {root}[/red]")
        raise typer.Exit(1)
    
    table = Table(title=f"Prompt 文件列表 ({root.relative_to(_PROMPTS_ROOT.parent)})")
    table.add_column("路径", style="cyan")
    table.add_column("类型", style="green")
    if show_metadata:
        table.add_column("版本", style="yellow")
        table.add_column("标题", style="dim")
    
    count = 0
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.suffix in (".md", ".j2"):
            rel_path = p.relative_to(_PROMPTS_ROOT)
            file_type = "模板" if p.suffix == ".j2" else "文本"
            
            if show_metadata:
                try:
                    asset = load_prompt_asset(str(rel_path))
                    version = asset.file_version or asset.metadata.version or "-"
                    title = asset.metadata.title[:30] if asset.metadata.title else "-"
                    table.add_row(str(rel_path), file_type, version, title)
                except Exception:
                    table.add_row(str(rel_path), file_type, "-", "-")
            else:
                table.add_row(str(rel_path), file_type)
            count += 1
    
    console.print(table)
    console.print(f"\n共 {count} 个文件")


@prompts_app.command("versions")
def list_versions(
    path: str = typer.Argument(..., help="Prompt 相对路径（如 system/core/global.md）"),
) -> None:
    """列出指定 prompt 的所有可用版本。"""
    versions = list_prompt_versions(path)
    
    if not versions:
        console.print(f"[yellow]未找到 {path} 的版本化文件[/yellow]")
        console.print("[dim]提示：版本化文件命名格式为 xxx_v1.2.3.md[/dim]")
        
        # 检查默认文件是否存在
        default_path = _PROMPTS_ROOT / path
        if default_path.exists():
            console.print(f"[green]✓ 默认版本存在: {path}[/green]")
        else:
            console.print(f"[red]✗ 默认文件不存在: {path}[/red]")
        return
    
    table = Table(title=f"版本列表: {path}")
    table.add_column("版本", style="cyan")
    table.add_column("文件名", style="dim")
    
    p = Path(path)
    for v in versions:
        versioned_name = f"{p.stem}_v{v}{p.suffix}"
        table.add_row(v, versioned_name)
    
    console.print(table)
    console.print(f"\n共 {len(versions)} 个版本")
    console.print(f"[dim]默认版本: {path}[/dim]")


@prompts_app.command("show")
def show_prompt(
    path: str = typer.Argument(..., help="Prompt 相对路径"),
    version: str = typer.Option("", "--version", "-v", help="指定版本"),
    raw: bool = typer.Option(False, "--raw", "-r", help="显示原始内容（含 front matter）"),
) -> None:
    """显示 prompt 内容。"""
    try:
        if raw:
            full_path = _PROMPTS_ROOT / path
            if version:
                p = Path(path)
                versioned_name = f"{p.stem}_v{version}{p.suffix}"
                full_path = _PROMPTS_ROOT / p.parent / versioned_name
            
            if not full_path.exists():
                console.print(f"[red]文件不存在: {full_path}[/red]")
                raise typer.Exit(1)
            
            content = full_path.read_text(encoding="utf-8")
        else:
            asset = load_prompt_asset(path, version=version if version else None)
            content = asset.content
            
            # 显示元数据
            if asset.metadata.title or asset.metadata.version:
                console.print(Panel(
                    f"[cyan]标题:[/cyan] {asset.metadata.title or '-'}\n"
                    f"[cyan]版本:[/cyan] {asset.file_version or asset.metadata.version or '-'}\n"
                    f"[cyan]层级:[/cyan] {asset.metadata.layer or '-'}",
                    title="元数据",
                    border_style="dim",
                ))
        
        # 语法高亮
        lexer = "jinja2" if path.endswith(".j2") else "markdown"
        syntax = Syntax(content, lexer, theme="monokai", line_numbers=True)
        console.print(syntax)
        
    except FileNotFoundError:
        console.print(f"[red]文件不存在: {path}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]读取失败: {e}[/red]")
        raise typer.Exit(1)


@prompts_app.command("validate")
def validate_prompts() -> None:
    """验证 prompt 目录结构是否符合规范。"""
    issues = []
    warnings = []
    
    # 检查必需的目录
    required_dirs = [
        "system/core",
        "system/role",
        "system/context",
        "user/stage",
        "user/intent",
    ]
    
    for d in required_dirs:
        dir_path = _PROMPTS_ROOT / d
        if not dir_path.exists():
            issues.append(f"缺失必需目录: {d}")
        elif not any(dir_path.iterdir()):
            warnings.append(f"目录为空: {d}")
    
    # 检查必需的文件
    required_files = [
        "system/core/global.md",
        "system/context/runtime.j2",
        "user/stage/planning.j2",
        "user/stage/execute_step.j2",
        "user/stage/intent_classify.j2",
    ]
    
    for f in required_files:
        file_path = _PROMPTS_ROOT / f
        if not file_path.exists():
            issues.append(f"缺失必需文件: {f}")
    
    # 检查旧目录（应该已删除）
    old_dirs = ["agent_loop", "classifier"]
    for d in old_dirs:
        dir_path = _PROMPTS_ROOT / d
        if dir_path.exists():
            files = list(dir_path.glob("*"))
            pycache = [f for f in files if f.name == "__pycache__"]
            other = [f for f in files if f.name != "__pycache__"]
            if other:
                warnings.append(f"旧目录未清理: {d}（包含 {len(other)} 个文件）")
            elif pycache:
                warnings.append(f"旧目录残留缓存: {d}/__pycache__")
    
    # 输出结果
    if issues:
        console.print("[red]❌ 验证失败[/red]")
        for issue in issues:
            console.print(f"  [red]• {issue}[/red]")
    else:
        console.print("[green]✓ 目录结构验证通过[/green]")
    
    if warnings:
        console.print("\n[yellow]⚠ 警告:[/yellow]")
        for warning in warnings:
            console.print(f"  [yellow]• {warning}[/yellow]")
    
    # 统计
    total_files = sum(1 for _ in _PROMPTS_ROOT.rglob("*") if _.is_file() and _.suffix in (".md", ".j2"))
    console.print(f"\n[dim]共 {total_files} 个 prompt 文件[/dim]")
    
    if issues:
        raise typer.Exit(1)


@prompts_app.command("pin")
def pin_version(
    path: str = typer.Argument(..., help="Prompt 相对路径"),
    version: str = typer.Argument(..., help="要锁定的版本号"),
) -> None:
    """锁定指定 prompt 到特定版本（创建符号链接或复制）。"""
    # 检查版本化文件是否存在
    p = Path(path)
    versioned_name = f"{p.stem}_v{version}{p.suffix}"
    versioned_path = _PROMPTS_ROOT / p.parent / versioned_name
    
    if not versioned_path.exists():
        console.print(f"[red]版本文件不存在: {versioned_path}[/red]")
        console.print("[dim]可用版本:[/dim]")
        versions = list_prompt_versions(path)
        if versions:
            for v in versions:
                console.print(f"  - {v}")
        else:
            console.print("  (无)")
        raise typer.Exit(1)
    
    # 复制版本化文件到默认文件
    default_path = _PROMPTS_ROOT / path
    import shutil
    
    # 备份原文件（如果存在）
    if default_path.exists():
        backup_path = default_path.with_suffix(default_path.suffix + ".bak")
        shutil.copy(default_path, backup_path)
        console.print(f"[dim]已备份原文件到: {backup_path.name}[/dim]")
    
    # 复制版本化文件
    shutil.copy(versioned_path, default_path)
    console.print(f"[green]✓ 已将 {path} 锁定到版本 {version}[/green]")


@prompts_app.command("unpin")
def unpin_version(
    path: str = typer.Argument(..., help="Prompt 相对路径"),
) -> None:
    """恢复到备份版本（取消锁定）。"""
    default_path = _PROMPTS_ROOT / path
    backup_path = default_path.with_suffix(default_path.suffix + ".bak")
    
    if not backup_path.exists():
        console.print(f"[yellow]未找到备份文件: {backup_path}[/yellow]")
        raise typer.Exit(1)
    
    import shutil
    shutil.copy(backup_path, default_path)
    backup_path.unlink()
    
    console.print(f"[green]✓ 已恢复 {path} 到备份版本[/green]")

