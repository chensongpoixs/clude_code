"""
Observability CLI commands - 可观测性相关命令

提供监控、指标、追踪等可观测性功能的CLI接口
"""
import typer
import time
from typing import Optional

from clude_code.config.config import CludeConfig
from clude_code.cli.cli_logging import get_cli_logger
from clude_code.core.project_paths import ProjectPaths, DEFAULT_PROJECT_ID

# 创建observability子应用
observability_app = typer.Typer(help="可观测性相关命令（监控、指标、追踪）")

# 创建metrics子应用
metrics_app = typer.Typer(help="指标监控相关命令")

# 添加回调来处理直接调用 metrics --hours 的情况
@metrics_app.callback(invoke_without_command=True)
def metrics_callback(
    ctx: typer.Context,
    hours: Optional[int] = typer.Option(None, "--hours", "-H", help="显示最近N小时的指标"),
    workspace: Optional[str] = typer.Option(None, "--workspace", help="指定工作区路径"),
    format: str = typer.Option("text", "--format", help="输出格式 (text/json)")
):
    """
    指标监控命令

    如果直接调用而不指定子命令，将显示指标数据列表。
    """
    # 如果没有指定子命令，执行默认的list功能
    if ctx.invoked_subcommand is None:
        # 调用list命令的功能
        metrics_list(hours=hours, workspace=workspace, format=format, limit=50)

observability_app.add_typer(metrics_app, name="metrics", help="指标监控命令")

# 创建profiles子应用
profiles_app = typer.Typer(help="性能分析相关命令")

# 添加回调来处理直接调用 profiles --type 的情况
@profiles_app.callback(invoke_without_command=True)
def profiles_callback(
    ctx: typer.Context,
    type_filter: Optional[str] = typer.Option(None, "--type", "-t", help="分析类型过滤 (cpu/memory/io/function)"),
    workspace: Optional[str] = typer.Option(None, "--workspace", help="指定工作区路径"),
    format: str = typer.Option("text", "--format", help="输出格式 (text/json)")
):
    """
    性能分析命令

    如果直接调用而不指定子命令，将显示分析记录列表。
    """
    # 如果没有指定子命令，执行默认的list功能
    if ctx.invoked_subcommand is None:
        # 直接执行list功能
        try:
            cfg = CludeConfig()
            if workspace:
                cfg.workspace_root = workspace

            # 尝试导入profiler模块
            try:
                from clude_code.observability.profiler import ProfileManager, ProfileType

                # 初始化profile管理器
                profile_manager = ProfileManager(cfg.workspace_root)

                # 获取所有记录
                records = profile_manager.get_records()

                # 应用类型过滤
                if type_filter:
                    try:
                        filter_type = ProfileType(type_filter.lower())
                        records = [r for r in records if r.profile_type == filter_type]
                    except ValueError:
                        typer.echo(f"❌ 无效的类型过滤器: {type_filter}", err=True)
                        typer.echo("可用的类型: cpu, memory, io, function")
                        raise typer.Exit(1)

                # 显示结果
                typer.echo("📊 性能分析记录")
                typer.echo("=" * 50)
                typer.echo(f"工作区: {cfg.workspace_root}")
                typer.echo(f"总记录数: {len(records)}")

                if type_filter:
                    typer.echo(f"类型过滤: {type_filter}")

                if not records:
                    typer.echo("\nℹ️  没有找到性能分析记录")
                    typer.echo("💡 提示: 使用 'observability profiles start --name <name> --type <type>' 开始分析")
                    return

                typer.echo("\n记录列表:")

                for i, record in enumerate(records, 1):
                    duration_str = ".3f" if record.duration else "进行中"
                    typer.echo(f"{i:2d}. {record.name} ({record.profile_type.value})")
                    typer.echo(f"    开始时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(record.start_time))}")
                    if record.duration:
                        typer.echo(f"    持续时间: {duration_str}")
                    typer.echo(f"    线程ID: {record.thread_id or 'N/A'}")
                    if record.data:
                        typer.echo(f"    额外数据: {len(record.data)} 项")
                    typer.echo()

            except ImportError:
                typer.echo("❌ 性能分析功能不可用（缺少依赖）")
                typer.echo("需要安装相关依赖包")

        except Exception as e:
            typer.echo(f"❌ 获取分析记录失败: {str(e)}", err=True)
            raise typer.Exit(1)

observability_app.add_typer(profiles_app, name="profiles", help="性能分析命令")


@observability_app.command("traces")
def traces(
    limit: int = typer.Option(50, "--limit", "-l", help="显示的追踪记录数量限制"),
    session: Optional[str] = typer.Option(None, "--session", "-s", help="过滤特定会话ID"),
    format: str = typer.Option("text", "--format", "-f", help="输出格式 (text/json)"),
    project_id: str = typer.Option(DEFAULT_PROJECT_ID, "--project-id", help="项目ID（用于隔离 trace/audit 路径）"),
    workspace: Optional[str] = typer.Option(None, "--workspace", help="指定工作区路径")
):
    """
    显示追踪记录

    显示Claude Code的执行追踪信息，包括工具调用、决策过程等。
    支持按会话过滤和数量限制。
    """
    try:
        cfg = CludeConfig()
        if workspace:
            cfg.workspace_root = workspace

        # 创建TraceLogger实例来读取追踪数据
        try:
            from clude_code.observability.trace import TraceLogger

            trace_logger = TraceLogger(str(cfg.workspace_root), "read_session", project_id=project_id)
            traces = trace_logger.read_traces(limit=limit, session_id=session)

            if format == "json":
                # JSON格式输出
                import json
                trace_data = {
                    "total_traces": len(traces),
                    "limit": limit,
                    "session_filter": session,
                    "traces": [
                        {
                            "timestamp": trace.timestamp,
                            "trace_id": trace.trace_id,
                            "session_id": trace.session_id,
                            "step": trace.step,
                            "event": trace.event,
                            "data": trace.data
                        }
                        for trace in traces
                    ]
                }
                typer.echo(json.dumps(trace_data, indent=2, ensure_ascii=False, default=str))
            else:
                # 文本格式输出
                typer.echo("🔍 Claude Code 追踪记录")
                typer.echo("=" * 60)
                typer.echo(f"工作区: {cfg.workspace_root}")
                typer.echo(f"总记录数: {len(traces)}")

                if session:
                    typer.echo(f"会话过滤: {session}")
                typer.echo(f"显示限制: {limit}")

                if not traces:
                    typer.echo("\nℹ️  没有找到追踪记录")
                    typer.echo("💡 提示: 运行Claude Code时会自动生成追踪记录")
                    return

                typer.echo("\n追踪记录:")
                typer.echo("-" * 60)

                for i, trace in enumerate(traces, 1):
                    typer.echo(f"{i:3d}. [{time.strftime('%H:%M:%S', time.localtime(trace.timestamp))}] {trace.event}")
                    typer.echo(f"     会话: {trace.session_id}")
                    typer.echo(f"     追踪ID: {trace.trace_id}")
                    typer.echo(f"     步骤: {trace.step}")

                    # 显示数据摘要
                    if trace.data:
                        data_keys = list(trace.data.keys())
                        if len(data_keys) <= 3:
                            data_summary = ", ".join(f"{k}: {str(v)[:50]}" for k, v in trace.data.items())
                        else:
                            data_summary = f"{data_keys[0]}, {data_keys[1]}, ... ({len(data_keys)} 项)"
                        typer.echo(f"     数据: {data_summary}")
                    else:
                        typer.echo("     数据: 无")

                    typer.echo()

        except ImportError:
            typer.echo("❌ 追踪功能不可用")
            typer.echo("追踪记录存储在: .clude/logs/trace.jsonl")

    except Exception as e:
        typer.echo(f"❌ 获取追踪记录失败: {str(e)}", err=True)
        raise typer.Exit(1)


@observability_app.command("audit-export")
def audit_export(
    limit: int = typer.Option(500, "--limit", "-l", help="最多读取的审计行数（从文件末尾开始统计并输出摘要）"),
    format: str = typer.Option("text", "--format", "-f", help="输出格式 (text/json)"),
    project_id: str = typer.Option(DEFAULT_PROJECT_ID, "--project-id", help="项目ID（用于隔离 audit 路径）"),
    workspace: Optional[str] = typer.Option(None, "--workspace", help="指定工作区路径"),
):
    """
    导出审计摘要报表（MVP）

    - 默认只依赖 audit.jsonl 的明文字段（timestamp/trace_id/session_id/project_id/event）
    - 如 data 被加密（data_enc），仍可统计 event 计数与时间范围
    """
    cfg = CludeConfig()
    if workspace:
        cfg.workspace_root = workspace

    paths = ProjectPaths(cfg.workspace_root, project_id, auto_create=False)
    audit_file = paths.audit_file()
    if not audit_file.exists():
        typer.echo(f"ℹ️  未找到审计文件: {audit_file}")
        raise typer.Exit(0)

    # 从末尾读取（简化：直接全读再截断；后续可优化为 seek）
    try:
        lines = audit_file.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception as e:
        typer.echo(f"❌ 读取审计文件失败: {type(e).__name__}: {e}", err=True)
        raise typer.Exit(1)

    if limit > 0:
        lines = lines[-limit:]

    total = 0
    parse_errors = 0
    encrypted = 0
    by_event: dict[str, int] = {}
    min_ts: int | None = None
    max_ts: int | None = None

    import json as _json

    for line in lines:
        if not line.strip():
            continue
        try:
            obj = _json.loads(line)
            total += 1
            ev = str(obj.get("event") or "")
            by_event[ev] = by_event.get(ev, 0) + 1
            ts = obj.get("timestamp")
            if isinstance(ts, int):
                min_ts = ts if min_ts is None else min(min_ts, ts)
                max_ts = ts if max_ts is None else max(max_ts, ts)
            if "data_enc" in obj:
                encrypted += 1
        except Exception:
            parse_errors += 1

    report = {
        "audit_file": str(audit_file),
        "project_id": project_id,
        "scanned_lines": len(lines),
        "parsed_events": total,
        "parse_errors": parse_errors,
        "encrypted_events": encrypted,
        "time_range": {"min_ts": min_ts, "max_ts": max_ts},
        "by_event": dict(sorted(by_event.items(), key=lambda kv: kv[1], reverse=True)),
    }

    if format == "json":
        typer.echo(_json.dumps(report, ensure_ascii=False, indent=2))
        return

    typer.echo("📋 审计摘要报表")
    typer.echo("=" * 60)
    typer.echo(f"项目ID: {project_id}")
    typer.echo(f"审计文件: {audit_file}")
    typer.echo(f"扫描行数: {len(lines)}")
    typer.echo(f"解析事件: {total}  解析失败: {parse_errors}  加密事件: {encrypted}")
    if min_ts and max_ts:
        typer.echo(f"时间范围: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(min_ts))}  ~  {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(max_ts))}")
    typer.echo("\n按事件类型计数（Top）：")
    for k, v in list(report["by_event"].items())[:30]:
        typer.echo(f"- {k or '<EMPTY>'}: {v}")


@observability_app.command("dashboard")
def dashboard(
    refresh: int = typer.Option(30, "--refresh", "-r", help="刷新间隔（秒）"),
    format: str = typer.Option("rich", "--format", "-f", help="显示格式 (rich/text/json)"),
    compact: bool = typer.Option(False, "--compact", "-c", help="紧凑模式"),
    workspace: Optional[str] = typer.Option(None, "--workspace", help="指定工作区路径")
):
    """
    显示可观测性仪表板

    提供系统状态、性能指标和分析数据的综合视图。
    支持实时刷新和多种显示格式。
    """
    try:
        cfg = CludeConfig()
        if workspace:
            cfg.workspace_root = workspace

        if format == "json":
            dashboard_data = collect_dashboard_data(cfg)
            import json
            typer.echo(json.dumps(dashboard_data, indent=2, ensure_ascii=False, default=str))
            return

        # 显示仪表板
        display_dashboard(cfg, format=format, compact=compact, refresh_interval=refresh)

    except Exception as e:
        typer.echo(f"❌ 仪表板显示失败: {str(e)}", err=True)
        raise typer.Exit(1)


def collect_dashboard_data(cfg: CludeConfig) -> dict:
    """收集仪表板数据"""
    dashboard_data = {
        "timestamp": time.time(),
        "workspace": cfg.workspace_root,
        "system_info": get_system_info(),
        "observability_status": {},
        "metrics_summary": {},
        "recent_profiles": [],
        "alerts": []
    }

    # 检查各个组件状态
    dashboard_data["observability_status"] = check_components_status(cfg)

    # 收集指标摘要
    dashboard_data["metrics_summary"] = collect_metrics_summary(cfg)

    # 获取最近的分析记录
    dashboard_data["recent_profiles"] = get_recent_profiles(cfg)

    # 检查告警
    dashboard_data["alerts"] = check_alerts(cfg)

    return dashboard_data


def get_system_info() -> dict:
    """获取系统信息"""
    try:
        import platform
        import psutil

        return {
            "platform": platform.platform(),
            "python_version": platform.python_version(),
            "cpu_count": psutil.cpu_count(),
            "memory_total": psutil.virtual_memory().total,
            "disk_usage": psutil.disk_usage('/')._asdict() if psutil.disk_usage('/') else None
        }
    except ImportError:
        return {
            "platform": platform.platform(),
            "python_version": platform.python_version(),
            "error": "psutil not available"
        }


def check_components_status(cfg: CludeConfig) -> dict:
    """检查各个组件状态"""
    status = {}

    # 检查指标系统
    try:
        from clude_code.observability.metrics import MetricsCollector
        MetricsCollector(str(cfg.workspace_root))
        status["metrics"] = {"status": "healthy", "message": "正常运行"}
    except Exception as e:
        status["metrics"] = {"status": "unhealthy", "message": f"异常: {str(e)}"}

    # 检查追踪系统
    try:
        from clude_code.observability.trace import TraceLogger
        TraceLogger(cfg.workspace_root, "dashboard_check")
        status["tracing"] = {"status": "healthy", "message": "正常运行"}
    except Exception as e:
        status["tracing"] = {"status": "degraded", "message": f"依赖缺失: {str(e)}"}

    # 检查审计系统
    try:
        from clude_code.observability.audit import AuditLogger
        AuditLogger(cfg.workspace_root, "dashboard_check")
        status["audit"] = {"status": "healthy", "message": "正常运行"}
    except Exception as e:
        status["audit"] = {"status": "degraded", "message": f"依赖缺失: {str(e)}"}

    # 检查性能分析系统
    try:
        from clude_code.observability.profiler import ProfileManager
        ProfileManager(cfg.workspace_root)
        status["profiler"] = {"status": "healthy", "message": "正常运行"}
    except Exception as e:
        status["profiler"] = {"status": "unhealthy", "message": f"异常: {str(e)}"}

    return status


def collect_metrics_summary(cfg: CludeConfig) -> dict:
    """收集指标摘要"""
    try:
        from clude_code.observability.metrics import MetricsCollector
        collector = MetricsCollector(str(cfg.workspace_root))
        points = collector.collect_all()

        # 按类型统计
        by_type = {}
        for point in points:
            type_name = point.metric_type.value
            by_type[type_name] = by_type.get(type_name, 0) + 1

        return {
            "total_points": len(points),
            "by_type": by_type,
            "last_updated": max((p.timestamp for p in points), default=None)
        }
    except Exception:
        return {"error": "无法收集指标摘要"}


def get_recent_profiles(cfg: CludeConfig) -> list:
    """获取最近的分析记录"""
    try:
        from clude_code.observability.profiler import ProfileManager
        manager = ProfileManager(cfg.workspace_root)
        records = manager.get_records(limit=5)

        return [
            {
                "name": r.name,
                "type": r.profile_type.value,
                "duration": ".2f" if r.duration else None,
                "timestamp": r.start_time
            }
            for r in records
        ]
    except Exception:
        return []


def check_alerts(cfg: CludeConfig) -> list:
    """检查系统告警"""
    alerts = []

    # 检查磁盘空间
    try:
        import psutil
        disk = psutil.disk_usage('/')
        if disk.percent > 90:
            alerts.append({
                "level": "critical",
                "message": f"磁盘空间不足: {disk.percent:.1f}%",
                "component": "system"
            })
        elif disk.percent > 80:
            alerts.append({
                "level": "warning",
                "message": f"磁盘空间警告: {disk.percent:.1f}%",
                "component": "system"
            })
    except ImportError:
        alerts.append({
            "level": "info",
            "message": "无法检查磁盘空间（缺少psutil）",
            "component": "system"
        })

    # 检查内存使用
    try:
        import psutil
        memory = psutil.virtual_memory()
        if memory.percent > 90:
            alerts.append({
                "level": "critical",
                "message": f"内存使用过高: {memory.percent:.1f}%",
                "component": "system"
            })
    except ImportError:
        pass

    return alerts


def display_dashboard(cfg: CludeConfig, format: str = "rich", compact: bool = False, refresh_interval: int = 30):
    """显示仪表板"""
    if format == "rich":
        display_rich_dashboard(cfg, compact, refresh_interval)
    else:
        display_text_dashboard(cfg, compact)


def display_rich_dashboard(cfg: CludeConfig, compact: bool, refresh_interval: int):
    """使用Rich库显示丰富的仪表板"""
    try:
        from rich.console import Console
        from rich.panel import Panel
        from rich.table import Table
        from rich.columns import Columns
        from rich.text import Text
        from rich.live import Live
        import time as time_module

        console = Console()

        def generate_dashboard():
            data = collect_dashboard_data(cfg)

            # 创建组件状态面板
            status_table = Table(title="组件状态")
            status_table.add_column("组件", style="cyan")
            status_table.add_column("状态", style="green")
            status_table.add_column("消息")

            for component, info in data["observability_status"].items():
                status_emoji = {
                    "healthy": "✅",
                    "degraded": "⚠️",
                    "unhealthy": "❌"
                }.get(info["status"], "❓")

                status_table.add_row(
                    component,
                    f"{status_emoji} {info['status']}",
                    info["message"]
                )

            # 创建指标摘要面板
            metrics_panel = Panel.fit(
                f"总指标点数: {data['metrics_summary'].get('total_points', 0)}\n"
                f"最后更新: {data['metrics_summary'].get('last_updated', 'N/A')}",
                title="指标摘要"
            )

            # 创建最近分析面板
            if data["recent_profiles"]:
                profiles_table = Table(title="最近分析")
                profiles_table.add_column("名称")
                profiles_table.add_column("类型")
                profiles_table.add_column("持续时间")
                profiles_table.add_column("时间")

                for profile in data["recent_profiles"]:
                    profiles_table.add_row(
                        profile["name"],
                        profile["type"],
                        profile["duration"] or "N/A",
                        time_module.strftime('%H:%M:%S', time_module.localtime(profile["timestamp"]))
                    )
            else:
                profiles_table = Panel.fit("暂无分析记录", title="最近分析")

            # 创建告警面板
            if data["alerts"]:
                alerts_text = ""
                for alert in data["alerts"]:
                    emoji = {"critical": "🚨", "warning": "⚠️", "info": "ℹ️"}.get(alert["level"], "❓")
                    alerts_text += f"{emoji} {alert['message']}\n"
                alerts_panel = Panel.fit(alerts_text.strip(), title="系统告警")
            else:
                alerts_panel = Panel.fit("✅ 无告警", title="系统告警")

            # 组合布局
            if compact:
                console.print(status_table)
                console.print(metrics_panel)
                console.print(profiles_table)
                console.print(alerts_panel)
            else:
                top_row = Columns([Panel.fit(status_table), metrics_panel])
                bottom_row = Columns([profiles_table, alerts_panel])
                console.print(top_row)
                console.print(bottom_row)

        if refresh_interval > 0:
            with Live(console=console, refresh_per_second=1, transient=False) as live:
                while True:
                    live.update(generate_dashboard())
                    time_module.sleep(refresh_interval)
        else:
            generate_dashboard()

    except ImportError:
        console.print("⚠️  Rich库不可用，使用文本模式")
        display_text_dashboard(cfg, compact)


def display_text_dashboard(cfg: CludeConfig, compact: bool):
    """显示文本模式的仪表板"""
    data = collect_dashboard_data(cfg)

    typer.echo("📊 可观测性仪表板")
    typer.echo("=" * 60)

    # 系统信息
    typer.echo("🖥️  系统信息:")
    sys_info = data["system_info"]
    typer.echo(f"  平台: {sys_info.get('platform', 'Unknown')}")
    typer.echo(f"  Python: {sys_info.get('python_version', 'Unknown')}")
    typer.echo(f"  CPU核心数: {sys_info.get('cpu_count', 'Unknown')}")
    typer.echo()

    # 组件状态
    typer.echo("🔧 组件状态:")
    for component, info in data["observability_status"].items():
        status_emoji = {
            "healthy": "✅",
            "degraded": "⚠️",
            "unhealthy": "❌"
        }.get(info["status"], "❓")
        typer.echo(f"  {status_emoji} {component}: {info['message']}")
    typer.echo()

    # 指标摘要
    typer.echo("📈 指标摘要:")
    metrics = data["metrics_summary"]
    if "error" not in metrics:
        typer.echo(f"  总指标点数: {metrics.get('total_points', 0)}")
        if metrics.get("by_type"):
            typer.echo("  按类型分布:")
            for type_name, count in metrics["by_type"].items():
                typer.echo(f"    {type_name}: {count}")
    else:
        typer.echo(f"  {metrics['error']}")
    typer.echo()

    # 最近分析
    if data["recent_profiles"]:
        typer.echo("🔍 最近分析:")
        for profile in data["recent_profiles"]:
            typer.echo(f"  {profile['name']} ({profile['type']}) - {profile['duration'] or 'N/A'}")
    else:
        typer.echo("🔍 最近分析: 暂无记录")

    # 告警
    if data["alerts"]:
        typer.echo()
        typer.echo("🚨 系统告警:")
        for alert in data["alerts"]:
            emoji = {"critical": "🚨", "warning": "⚠️", "info": "ℹ️"}.get(alert["level"], "❓")
            typer.echo(f"  {emoji} {alert['message']}")
    else:
        typer.echo()
        typer.echo("✅ 系统告警: 无")


@metrics_app.command("status")
def metrics_status(
    workspace: Optional[str] = typer.Option(None, "--workspace", help="指定工作区路径"),
    format: str = typer.Option("text", "--format", help="输出格式 (text/json)")
) -> None:
    """
    显示指标系统状态

    显示当前的指标收集状态和系统健康状况。
    """
    try:
        # 获取配置
        cfg = CludeConfig()
        if workspace:
            cfg.workspace_root = workspace

        # 尝试导入指标收集器
        try:
            from clude_code.observability.metrics import MetricsCollector
            metrics_collector = MetricsCollector(str(cfg.workspace_root))

            # 注册一些示例指标
            counter = metrics_collector.counter("cli_status_counter", "CLI状态检查计数器")
            gauge = metrics_collector.gauge("cli_status_gauge", "CLI状态仪表盘")

            # 增加一些测试数据
            counter.inc()
            gauge.set(100.0)

            # 收集所有指标
            points = metrics_collector.collect_all()

            status_info = {
                "metrics_enabled": True,
                "workspace_root": cfg.workspace_root,
                "total_registered_metrics": len(metrics_collector._metrics),
                "total_collected_points": len(points),
                "status": "healthy"
            }
        except ImportError:
            status_info = {
                "metrics_enabled": False,
                "workspace_root": cfg.workspace_root,
                "error": "MetricsCollector不可用（缺少依赖）",
                "status": "unhealthy"
            }
        except Exception as e:
            status_info = {
                "metrics_enabled": False,
                "workspace_root": cfg.workspace_root,
                "error": f"指标系统错误: {str(e)}",
                "status": "unhealthy"
            }

        # 根据格式输出
        if format == "json":
            import json
            typer.echo(json.dumps(status_info, indent=2, ensure_ascii=False, default=str))
        else:
            # 文本格式输出
            typer.echo("📊 Claude Code 指标系统状态")
            typer.echo("=" * 50)

            typer.echo(f"工作区: {status_info['workspace_root']}")
            typer.echo(f"指标系统: {'启用' if status_info.get('metrics_enabled', False) else '禁用'}")

            if status_info.get('status') == 'healthy':
                typer.echo(f"已注册指标数: {status_info.get('total_registered_metrics', 0)}")
                typer.echo(f"收集到的数据点数: {status_info.get('total_collected_points', 0)}")
                typer.echo("✅ 指标系统运行正常")
            else:
                typer.echo(f"❌ 指标系统异常: {status_info.get('error', '未知错误')}")

    except Exception as e:
        typer.echo(f"❌ 获取指标状态失败: {str(e)}", err=True)
        raise typer.Exit(1)


@metrics_app.command("list")
def metrics_list(
    hours: Optional[int] = typer.Option(None, "--hours", "-H", help="显示最近N小时的指标"),
    workspace: Optional[str] = typer.Option(None, "--workspace", help="指定工作区路径"),
    format: str = typer.Option("text", "--format", help="输出格式 (text/json)"),
    limit: int = typer.Option(50, "--limit", "-l", help="限制显示的数量")
) -> None:
    """
    列出指标数据

    显示收集到的指标数据点，支持时间范围和数量限制。
    """
    try:
        # 获取配置
        cfg = CludeConfig()
        if workspace:
            cfg.workspace_root = workspace

        # 计算时间范围
        start_time = None
        if hours:
            start_time = time.time() - (hours * 3600)

        # 尝试导入指标收集器
        try:
            from clude_code.observability.metrics import MetricsCollector
            metrics_collector = MetricsCollector(str(cfg.workspace_root))

            # 注册一些示例指标并生成数据
            counter = metrics_collector.counter("request_counter", "请求计数器")
            gauge = metrics_collector.gauge("response_time_gauge", "响应时间仪表盘")

            # 生成一些示例数据
            counter.inc(5)  # 增加5次请求
            gauge.set(150.0)  # 设置响应时间为150ms

            # 收集所有指标
            points = metrics_collector.collect_all()

            # 应用时间过滤（如果有时间范围）
            if start_time:
                points = [p for p in points if p.timestamp >= start_time]

            # 按时间排序（最新的在前）
            points.sort(key=lambda p: p.timestamp, reverse=True)

            # 限制数量
            points = points[:limit]

            metrics_data = {
                "total_points": len(points),
                "time_range_hours": hours,
                "limit": limit,
                "points": [
                    {
                        "name": p.name,
                        "type": p.metric_type.value,
                        "value": p.value,
                        "timestamp": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(p.timestamp)),
                        "labels": p.labels,
                        "help_text": p.help_text
                    }
                    for p in points
                ]
            }

            # 根据格式输出
            if format == "json":
                import json
                typer.echo(json.dumps(metrics_data, indent=2, ensure_ascii=False, default=str))
            else:
                # 文本格式输出
                typer.echo("📊 指标数据列表")
                typer.echo("=" * 60)

                if hours:
                    typer.echo(f"时间范围: 最近 {hours} 小时")
                typer.echo(f"显示数量: {len(points)} / {limit}")

                if not points:
                    typer.echo("\nℹ️  没有找到指标数据")
                    return

                typer.echo("\n指标数据:")
                typer.echo("-" * 60)

                for i, point in enumerate(points, 1):
                    typer.echo(f"{i:2d}. {point.name}")
                    typer.echo(f"    类型: {point.metric_type.value}")
                    typer.echo(f"    值: {point.value}")
                    typer.echo(f"    时间: {time.strftime('%H:%M:%S', time.localtime(point.timestamp))}")
                    if point.labels:
                        typer.echo(f"    标签: {point.labels}")
                    if point.help_text:
                        typer.echo(f"    描述: {point.help_text}")
                    typer.echo()

        except ImportError:
            typer.echo("❌ 指标系统不可用（缺少依赖）")
            typer.echo("需要安装相关依赖包")

    except Exception as e:
        typer.echo(f"❌ 获取指标数据失败: {str(e)}", err=True)
        raise typer.Exit(1)


@observability_app.command("logs")
def logs(
    level: str = typer.Option("info", "--level", help="日志级别 (debug/info/warning/error)"),
    follow: bool = typer.Option(False, "--follow", "-f", help="实时跟踪日志"),
    lines: int = typer.Option(100, "--lines", "-n", help="显示最近的行数"),
    workspace: Optional[str] = typer.Option(None, "--workspace", help="指定工作区路径")
) -> None:
    """
    查看可观测性日志

    显示应用的日志信息，包括审计日志、追踪日志等。
    """
    try:
        cfg = CludeConfig()
        if workspace:
            cfg.workspace_root = workspace

        logger = get_cli_logger().console

        # 这里可以实现日志查看功能
        # 暂时显示一个简单的状态
        typer.echo("📝 可观测性日志查看")
        typer.echo("=" * 30)
        typer.echo(f"工作区: {cfg.workspace_root}")
        typer.echo(f"日志级别: {level}")
        typer.echo(f"显示行数: {lines}")
        typer.echo(f"实时跟踪: {'是' if follow else '否'}")
        typer.echo()
        typer.echo("ℹ️  日志查看功能正在开发中...")

    except Exception as e:
        typer.echo(f"❌ 查看日志失败: {str(e)}", err=True)
        raise typer.Exit(1)


@observability_app.command("health")
def health_check(
    workspace: Optional[str] = typer.Option(None, "--workspace", help="指定工作区路径"),
    detailed: bool = typer.Option(False, "--detailed", help="显示详细健康信息")
) -> None:
    """
    执行健康检查

    检查可观测性系统的各个组件是否正常运行。
    """
    try:
        cfg = CludeConfig()
        if workspace:
            cfg.workspace_root = workspace

        health_status = {
            "overall_status": "healthy",
            "components": {}
        }

        # 检查指标系统
        try:
            from clude_code.observability.metrics import MetricsCollector
            metrics = MetricsCollector(str(cfg.workspace_root))
            health_status["components"]["metrics"] = {
                "status": "healthy",
                "message": "指标系统正常运行"
            }
        except ImportError:
            health_status["components"]["metrics"] = {
                "status": "degraded",
                "message": "指标系统依赖缺失（psutil）"
            }
        except Exception as e:
            health_status["components"]["metrics"] = {
                "status": "unhealthy",
                "message": f"指标系统异常: {str(e)}"
            }
            health_status["overall_status"] = "unhealthy"

        # 检查追踪系统
        try:
            from clude_code.observability.trace import TraceLogger
            trace = TraceLogger(cfg.workspace_root, "health_check")
            health_status["components"]["tracing"] = {
                "status": "healthy",
                "message": "追踪系统正常运行"
            }
        except ImportError:
            health_status["components"]["tracing"] = {
                "status": "degraded",
                "message": "追踪系统依赖缺失"
            }
        except Exception as e:
            health_status["components"]["tracing"] = {
                "status": "unhealthy",
                "message": f"追踪系统异常: {str(e)}"
            }
            health_status["overall_status"] = "degraded"

        # 检查审计系统
        try:
            from clude_code.observability.audit import AuditLogger
            audit = AuditLogger(cfg.workspace_root, "health_check")
            health_status["components"]["audit"] = {
                "status": "healthy",
                "message": "审计系统正常运行"
            }
        except ImportError:
            health_status["components"]["audit"] = {
                "status": "degraded",
                "message": "审计系统依赖缺失"
            }
        except Exception as e:
            health_status["components"]["audit"] = {
                "status": "unhealthy",
                "message": f"审计系统异常: {str(e)}"
            }
            health_status["overall_status"] = "degraded"

        # 输出结果
        if health_status["overall_status"] == "healthy":
            typer.echo("✅ 可观测性系统健康检查通过")
        elif health_status["overall_status"] == "degraded":
            typer.echo("⚠️  可观测性系统部分功能可用")
        else:
            typer.echo("❌ 可观测性系统健康检查失败")

        if detailed:
            typer.echo()
            typer.echo("详细组件状态:")
            for component, status in health_status["components"].items():
                if status["status"] == "healthy":
                    status_icon = "✅"
                elif status["status"] == "degraded":
                    status_icon = "⚠️"
                else:
                    status_icon = "❌"
                typer.echo(f"  {status_icon} {component}: {status['message']}")

    except Exception as e:
        typer.echo(f"❌ 健康检查失败: {str(e)}", err=True)
        raise typer.Exit(1)


@profiles_app.command("list")
def profiles_list(
    workspace: Optional[str] = typer.Option(None, "--workspace", help="指定工作区路径"),
    type_filter: Optional[str] = typer.Option(None, "--type", help="按类型过滤 (cpu/memory/io/function)")
) -> None:
    """
    列出性能分析记录

    显示所有可用的性能分析记录，支持按类型过滤。
    """
    try:
        cfg = CludeConfig()
        if workspace:
            cfg.workspace_root = workspace

        # 尝试导入profiler模块
        try:
            from clude_code.observability.profiler import ProfileManager, ProfileType

            # 初始化profile管理器
            profile_manager = ProfileManager(cfg.workspace_root)

            # 获取所有记录
            records = profile_manager.get_records()

            # 应用类型过滤
            if type_filter:
                try:
                    filter_type = ProfileType(type_filter.lower())
                    records = [r for r in records if r.profile_type == filter_type]
                except ValueError:
                    typer.echo(f"❌ 无效的类型过滤器: {type_filter}", err=True)
                    typer.echo("可用的类型: cpu, memory, io, function")
                    raise typer.Exit(1)

            # 显示结果
            typer.echo("📊 性能分析记录")
            typer.echo("=" * 50)
            typer.echo(f"工作区: {cfg.workspace_root}")
            typer.echo(f"总记录数: {len(records)}")

            if type_filter:
                typer.echo(f"类型过滤: {type_filter}")

            if not records:
                typer.echo("\nℹ️  没有找到性能分析记录")
                return

            typer.echo("\n记录列表:")

            for i, record in enumerate(records, 1):
                duration_str = ".3f" if record.duration else "进行中"
                typer.echo(f"{i:2d}. {record.name} ({record.profile_type.value})")
                typer.echo(f"    开始时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(record.start_time))}")
                if record.duration:
                    typer.echo(f"    持续时间: {duration_str}")
                typer.echo(f"    线程ID: {record.thread_id or 'N/A'}")
                if record.data:
                    typer.echo(f"    额外数据: {len(record.data)} 项")
                typer.echo()

        except ImportError:
            typer.echo("❌ 性能分析功能不可用（缺少依赖）")
            typer.echo("需要安装相关依赖包")

    except Exception as e:
        typer.echo(f"❌ 获取分析记录失败: {str(e)}", err=True)
        raise typer.Exit(1)


@profiles_app.command("start")
def profiles_start(
    name: str = typer.Option(..., "--name", "-n", help="分析名称"),
    type: str = typer.Option("function", "--type", "-t", help="分析类型 (cpu/memory/io/function)"),
    workspace: Optional[str] = typer.Option(None, "--workspace", help="指定工作区路径")
) -> None:
    """
    开始性能分析

    启动指定类型的性能分析会话。
    """
    try:
        cfg = CludeConfig()
        if workspace:
            cfg.workspace_root = workspace

        # 验证类型
        valid_types = ["cpu", "memory", "io", "function"]
        if type not in valid_types:
            typer.echo(f"❌ 无效的分析类型: {type}", err=True)
            typer.echo(f"可用类型: {', '.join(valid_types)}")
            raise typer.Exit(1)

        # 尝试导入profiler模块
        try:
            from clude_code.observability.profiler import ProfileManager, ProfileType

            # 初始化profile管理器
            profile_manager = ProfileManager(cfg.workspace_root)

            # 开始分析
            profile_type = ProfileType(type)
            success = profile_manager.start_profiling(name, profile_type)
            if not success:
                typer.echo(f"❌ 无法启动 {type} 类型的分析")
                typer.echo("可能原因: 分析已在运行，或缺少依赖（如cProfile）")
                return

            typer.echo("✅ 性能分析已启动")
            typer.echo(f"分析名称: {name}")
            typer.echo(f"分析类型: {type}")
            typer.echo("使用 'observability profiles stop --type {type}' 停止分析")

        except ImportError:
            typer.echo("❌ 性能分析功能不可用（缺少依赖）")

    except Exception as e:
        typer.echo(f"❌ 启动分析失败: {str(e)}", err=True)
        raise typer.Exit(1)


@profiles_app.command("stop")
def profiles_stop(
    type: str = typer.Option(..., "--type", "-t", help="分析类型 (cpu/memory/io/function)"),
    workspace: Optional[str] = typer.Option(None, "--workspace", help="指定工作区路径")
) -> None:
    """
    停止性能分析

    停止指定类型的性能分析会话并显示结果。
    """
    try:
        cfg = CludeConfig()
        if workspace:
            cfg.workspace_root = workspace

        # 验证类型
        valid_types = ["cpu", "memory", "io", "function"]
        if type not in valid_types:
            typer.echo(f"❌ 无效的分析类型: {type}", err=True)
            typer.echo(f"可用类型: {', '.join(valid_types)}")
            raise typer.Exit(1)

        # 尝试导入profiler模块
        try:
            from clude_code.observability.profiler import ProfileManager, ProfileType

            # 初始化profile管理器
            profile_manager = ProfileManager(cfg.workspace_root)

            # 停止分析
            profile_type = ProfileType(type)
            record = profile_manager.stop_profiling(profile_type)

            if record:
                typer.echo("✅ 性能分析已停止")
                typer.echo(f"分析名称: {record.name}")
                typer.echo(f"分析类型: {record.profile_type.value}")
                typer.echo(".3f")
                if record.data:
                    typer.echo("分析数据:")
                    for key, value in record.data.items():
                        typer.echo(f"  {key}: {value}")
            else:
                typer.echo(f"❌ {type} 类型的分析未在运行")

        except ImportError:
            typer.echo("❌ 性能分析功能不可用（缺少依赖）")

    except Exception as e:
        typer.echo(f"❌ 停止分析失败: {str(e)}", err=True)
        raise typer.Exit(1)


@profiles_app.command("report")
def profiles_report(
    type: Optional[str] = typer.Option(None, "--type", "-t", help="分析类型 (cpu/memory/io/function)"),
    limit: int = typer.Option(10, "--limit", "-l", help="显示记录数量限制"),
    workspace: Optional[str] = typer.Option(None, "--workspace", help="指定工作区路径"),
    format: str = typer.Option("text", "--format", help="输出格式 (text/json)")
) -> None:
    """
    生成性能分析报告

    显示最近的性能分析记录。
    """
    try:
        cfg = CludeConfig()
        if workspace:
            cfg.workspace_root = workspace

        # 尝试导入profiler模块
        try:
            from clude_code.observability.profiler import ProfileManager, ProfileType

            # 初始化profile管理器
            profile_manager = ProfileManager(cfg.workspace_root)

            # 获取记录
            profile_type = ProfileType(type) if type else None
            records = profile_manager.get_records(profile_type=profile_type, limit=limit)

            if not records:
                typer.echo("ℹ️  没有找到性能分析记录")
                return

            # 生成报告
            report_data = {
                "total_records": len(records),
                "filter_type": type,
                "records": []
            }

            for record in records:
                record_data = {
                    "name": record.name,
                    "type": record.profile_type.value,
                    "start_time": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(record.start_time)),
                    "duration": ".3f" if record.duration else "N/A",
                    "thread_id": record.thread_id,
                    "data_points": len(record.data)
                }
                report_data["records"].append(record_data)

            if format == "json":
                import json
                typer.echo(json.dumps(report_data, indent=2, ensure_ascii=False, default=str))
            else:
                typer.echo("📊 性能分析报告")
                typer.echo("=" * 50)
                typer.echo(f"总记录数: {report_data['total_records']}")
                if type:
                    typer.echo(f"类型过滤: {type}")

                typer.echo("\n最近记录:")
                for i, record_data in enumerate(report_data["records"], 1):
                    typer.echo(f"{i}. {record_data['name']} ({record_data['type']})")
                    typer.echo(f"   时间: {record_data['start_time']}")
                    typer.echo(f"   持续时间: {record_data['duration']}")
                    typer.echo(f"   数据点: {record_data['data_points']}")
                    typer.echo()

        except ImportError:
            typer.echo("❌ 性能分析功能不可用（缺少依赖）")

    except Exception as e:
        typer.echo(f"❌ 生成报告失败: {str(e)}", err=True)
        raise typer.Exit(1)