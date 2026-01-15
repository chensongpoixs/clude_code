"""
可观测性 CLI 命令
提供查询和管理可观测性数据的命令行接口
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import print as rprint

from clude_code.config import CludeConfig
from clude_code.observability.integration import get_observability_manager
from clude_code.observability.metrics_storage import get_metrics_manager, MetricsQuery
from clude_code.observability.profiler import get_profile_manager, ProfileType
from clude_code.observability.logger import get_logger

console = Console()


def create_config() -> CludeConfig:
    """创建配置对象"""
    try:
        return CludeConfig()
    except Exception as e:
        console.print(f"[red]Error creating config: {e}[/red]")
        raise typer.Exit(1)


def format_duration(seconds: float) -> str:
    """格式化持续时间"""
    if seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    elif seconds < 60:
        return f"{seconds:.2f}s"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}m"
    else:
        hours = seconds / 3600
        return f"{hours:.1f}h"


def format_bytes(bytes_value: int) -> str:
    """格式化字节数"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_value < 1024:
            return f"{bytes_value:.1f} {unit}"
        bytes_value /= 1024
    return f"{bytes_value:.1f} TB"


def show_metrics_status(
    hours: int = typer.Option(1, "--hours", "-h", help="时间范围（小时）"),
    workspace_root: str = typer.Option(".", "--workspace", "-w", help="工作区根目录")
) -> None:
    """显示指标状态"""
    cfg = create_config()
    cfg.workspace_root = workspace_root
    
    try:
        manager = get_observability_manager(cfg)
        summary = manager.get_metrics_summary(hours)
        
        # 创建指标表格
        metrics_table = Table(show_header=True, title="指标摘要")
        metrics_table.add_column("指标", style="bold")
        metrics_table.add_column("值", justify="right")
        metrics_table.add_column("说明")
        
        metrics_table.add_row(
            "LLM 请求",
            str(summary["llm_requests"]),
            "过去{}小时的LLM请求总数".format(hours)
        )
        
        metrics_table.add_row(
            "LLM 平均耗时",
            format_duration(summary["llm_avg_duration"]),
            "过去{}小时的LLM平均响应时间".format(hours)
        )
        
        metrics_table.add_row(
            "LLM 最大耗时",
            format_duration(summary["llm_max_duration"]),
            "过去{}小时的LLM最大响应时间".format(hours)
        )
        
        metrics_table.add_row(
            "工具调用",
            str(summary["tool_calls"]),
            "过去{}小时的总工具调用次数".format(hours)
        )
        
        metrics_table.add_row(
            "工具错误",
            str(summary["tool_errors"]),
            "过去{}小时的总工具错误次数".format(hours)
        )
        
        metrics_table.add_row(
            "任务执行",
            str(summary["task_executions"]),
            "过去{}小时的总任务执行次数".format(hours)
        )
        
        console.print(metrics_table)
        
    except Exception as e:
        console.print(f"[red]Error getting metrics status: {e}[/red]")
        raise typer.Exit(1)


def show_traces(
    limit: int = typer.Option(50, "--limit", "-l", help="显示的追踪数量"),
    workspace_root: str = typer.Option(".", "--workspace", "-w", help="工作区根目录")
) -> None:
    """显示追踪数据"""
    cfg = create_config()
    cfg.workspace_root = workspace_root
    
    try:
        # 读取追踪文件
        traces_file = Path(workspace_root) / ".clude" / "traces" / "traces.jsonl"
        
        if not traces_file.exists():
            console.print("[yellow]没有找到追踪数据文件[/yellow]")
            return
        
        traces = []
        with open(traces_file, 'r') as f:
            for line in f:
                try:
                    trace = json.loads(line.strip())
                    traces.append(trace)
                except json.JSONDecodeError:
                    continue
        
        # 按时间排序
        traces.sort(key=lambda t: t.get("start_time", 0), reverse=True)
        
        # 限制数量
        traces = traces[:limit]
        
        # 创建追踪表格
        traces_table = Table(show_header=True, title="追踪数据")
        traces_table.add_column("时间", style="dim")
        traces_table.add_column("名称", style="bold")
        traces_table.add_column("类型")
        traces_table.add_column("持续时间")
        traces_table.add_column("状态")
        
        for trace in traces:
            start_time = trace.get("start_time", 0)
            duration = trace.get("duration", 0)
            name = trace.get("name", "")
            kind = trace.get("kind", "")
            status = trace.get("status", "OK")
            
            time_str = time.strftime("%H:%M:%S", time.localtime(start_time))
            duration_str = format_duration(duration) if duration else "N/A"
            
            # 根据状态设置颜色
            status_style = "green" if status == "OK" else "red"
            status_text = f"[{status_style}]{status}[/{status_style}]"
            
            traces_table.add_row(time_str, name, kind, duration_str, status_text)
        
        console.print(traces_table)
        
    except Exception as e:
        console.print(f"[red]Error showing traces: {e}[/red]")
        raise typer.Exit(1)


def show_profiles(
    profile_type: str = typer.Option("function", "--type", "-t", help="分析类型 (cpu, memory, io, function)"),
    limit: int = typer.Option(10, "--limit", "-l", help="显示的分析记录数量"),
    workspace_root: str = typer.Option(".", "--workspace", "-w", help="工作区根目录")
) -> None:
    """显示性能分析数据"""
    cfg = create_config()
    cfg.workspace_root = workspace_root
    
    try:
        # 解析分析类型
        try:
            ptype = ProfileType(profile_type)
        except ValueError:
            console.print(f"[red]无效的分析类型: {profile_type}[/red]")
            console.print("可用的分析类型: cpu, memory, io, function")
            raise typer.Exit(1)
        
        manager = get_profile_manager(cfg)
        summary = manager.get_profile_summary(ptype)
        
        if not summary["profiles"]:
            console.print(f"[yellow]没有找到 {profile_type} 类型的性能分析记录[/yellow]")
            return
        
        # 创建分析表格
        profiles_table = Table(show_header=True, title=f"{profile_type.upper()} 性能分析")
        profiles_table.add_column("名称", style="bold")
        profiles_table.add_column("持续时间")
        profiles_table.add_column("时间")
        
        for profile in summary["profiles"][:limit]:
            name = profile["name"]
            duration = profile["duration"]
            timestamp = profile["timestamp"]
            
            duration_str = format_duration(duration) if duration else "N/A"
            time_str = time.strftime("%H:%M:%S", time.localtime(timestamp))
            
            profiles_table.add_row(name, duration_str, time_str)
        
        console.print(profiles_table)
        
    except Exception as e:
        console.print(f"[red]Error showing profiles: {e}[/red]")
        raise typer.Exit(1)


def export_metrics(
    format: str = typer.Option("prometheus", "--format", "-f", help="导出格式 (prometheus, json)"),
    hours: int = typer.Option(1, "--hours", "-h", help="时间范围（小时）"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="输出文件路径"),
    workspace_root: str = typer.Option(".", "--workspace", "-w", help="工作区根目录")
) -> None:
    """导出指标数据"""
    cfg = create_config()
    cfg.workspace_root = workspace_root
    
    try:
        manager = get_observability_manager(cfg)
        exported_data = manager.export_metrics(format, hours)
        
        if output:
            # 写入文件
            output_path = Path(output)
            with open(output_path, 'w') as f:
                f.write(exported_data)
            console.print(f"[green]指标数据已导出到: {output_path}[/green]")
        else:
            # 输出到控制台
            console.print(Panel(exported_data, title=f"指标数据 ({format} 格式)"))
        
    except Exception as e:
        console.print(f"[red]Error exporting metrics: {e}[/red]")
        raise typer.Exit(1)


def cleanup_data(
    days: int = typer.Option(7, "--days", "-d", help="保留天数"),
    workspace_root: str = typer.Option(".", "--workspace", "-w", help="工作区根目录")
) -> None:
    """清理过期的可观测性数据"""
    cfg = create_config()
    cfg.workspace_root = workspace_root
    
    try:
        # 清理指标数据
        metrics_manager = get_metrics_manager(workspace_root)
        metrics_removed = metrics_manager.cleanup(retention_hours=days * 24)
        console.print(f"[green]已清理 {metrics_removed} 条过期指标数据[/green]")
        
        # 清理性能分析数据
        profile_manager = get_profile_manager(workspace_root)
        profiles_removed = profile_manager.clear_records()
        console.print(f"[green]已清理 {profiles_removed} 条性能分析记录[/green]")
        
        # 清理追踪文件（简化实现，实际应用中可能需要更复杂的逻辑）
        traces_dir = Path(workspace_root) / ".clude" / "traces"
        if traces_dir.exists():
            cutoff_time = time.time() - days * 24 * 3600
            traces_removed = 0
            
            for trace_file in traces_dir.glob("*.jsonl"):
                try:
                    file_time = trace_file.stat().st_mtime
                    if file_time < cutoff_time:
                        trace_file.unlink()
                        traces_removed += 1
                except Exception as e:
                    console.print(f"[yellow]清理文件 {trace_file} 时出错: {e}[/yellow]")
            
            console.print(f"[green]已清理 {traces_removed} 个追踪文件[/green]")
        
    except Exception as e:
        console.print(f"[red]Error cleaning up data: {e}[/red]")
        raise typer.Exit(1)


def show_dashboard(
    workspace_root: str = typer.Option(".", "--workspace", "-w", help="工作区根目录")
) -> None:
    """显示可观测性仪表板"""
    cfg = create_config()
    cfg.workspace_root = workspace_root
    
    try:
        manager = get_observability_manager(cfg)
        
        # 获取各种摘要数据
        metrics_summary = manager.get_metrics_summary(hours=1)
        trace_summary = manager.get_trace_summary(hours=1)
        profile_summary = manager.get_profile_summary()
        
        # 创建仪表板布局
        # 指标面板
        metrics_panel = Panel(
            f"""[bold]LLM 请求:[/bold] {metrics_summary['llm_requests']}
[bold]工具调用:[/bold] {metrics_summary['tool_calls']}
[bold]任务执行:[/bold] {metrics_summary['task_executions']}
[bold]活跃会话:[/bold] {metrics_summary.get('active_sessions', 'N/A')}""",
            title="📊 实时指标",
            border_style="blue"
        )
        
        # 性能面板
        recent_profiles = profile_summary.get("profiles", [])[:3]
        profile_lines = []
        for profile in recent_profiles:
            duration = format_duration(profile["duration"]) if profile["duration"] else "N/A"
            profile_lines.append(f"[bold]{profile['name']}:[/bold] {duration}")
        
        performance_panel = Panel(
            "\n".join(profile_lines) if profile_lines else "暂无性能数据",
            title="⚡ 性能分析",
            border_style="green"
        )
        
        # 状态面板
        status_lines = [
            f"[bold]工作区:[/bold] {workspace_root}",
            f"[bold]指标存储:[/bold] 文件",
            f"[bold]追踪存储:[/bold] 文件",
            f"[bold]数据保留:[/bold] 7天"
        ]
        
        status_panel = Panel(
            "\n".join(status_lines),
            title="🔧 系统状态",
            border_style="yellow"
        )
        
        # 显示面板
        console.print(metrics_panel)
        console.print(performance_panel)
        console.print(status_panel)
        
    except Exception as e:
        console.print(f"[red]Error showing dashboard: {e}[/red]")
        raise typer.Exit(1)


# 创建 Typer 应用
app = typer.Typer(help="clude-code 可观测性命令")
app.command(name="metrics")(show_metrics_status)
app.command(name="traces")(show_traces)
app.command(name="profiles")(show_profiles)
app.command(name="export")(export_metrics)
app.command(name="cleanup")(cleanup_data)
app.command(name="dashboard")(show_dashboard)


if __name__ == "__main__":
    app()