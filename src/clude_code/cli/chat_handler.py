from typing import Any
import typer
from rich.console import Console
from rich.live import Live
from rich.prompt import Confirm

from clude_code.config import CludeConfig
from clude_code.orchestrator.agent_loop import AgentLoop
from clude_code.cli.live_view import LiveDisplay
from clude_code.cli.utils import select_model_interactively
from clude_code.cli.theme import CLAUDE_THEME, create_welcome_text, create_status_bar, create_ready_message
from clude_code.cli.animations import AnimatedWelcome, TypewriterEffect, FadeEffect
from clude_code.cli.shortcuts import ShortcutHandler, ShortcutAction, PromptResult
from clude_code.cli.config_manager import get_config_manager
from clude_code.cli.cli_logging import get_cli_logger

# 使用主题化的控制台
console = Console(theme=CLAUDE_THEME)

class ChatHandler:
    """
    负责处理交互式聊天循环与 AgentLoop 的集成。
    支持动画界面、快捷键和配置管理。
    """
    def __init__(self, cfg: CludeConfig):
        self.cfg = cfg
        self.agent = AgentLoop(cfg)

        # 初始化统一的日志系统
        self.cli_logger = get_cli_logger()

        # 初始化新功能组件
        self.config_manager = get_config_manager()
        self.shortcut_handler = ShortcutHandler(console)
        self.animated_welcome = AnimatedWelcome(console)

        # 会话状态
        self.session_id = self._generate_session_id()
        self.debug_mode = False

    def select_model_interactively(self) -> None:
        """调用公共工具进行交互式模型选择。"""
        select_model_interactively(self.cfg, self.cli_logger.console)

    def _show_welcome(self) -> None:
        """显示动画欢迎界面"""
        try:
            # 检查配置是否启用动画
            if self.config_manager.get_config_value("ui.show_animations"):
                self.animated_welcome.show_welcome(self.cfg)
            else:
                # 静态欢迎界面
                console.print(create_welcome_text())
                console.print(create_status_bar(self.cfg))
                console.print()
                console.print(create_ready_message())
                console.print()
        except Exception as e:
            # 降级到简单欢迎
            console.print("[bold cyan]Clude Code - 本地编程代理 CLI[/bold cyan]\n")
            console.print(f"版本: {getattr(self.cfg, '__version__', '0.1.0')}\n")
            console.print(f"模型: {self.cfg.llm.model}\n")
            console.print(f"工作区: {self.cfg.workspace_root}\n")
            console.print("[green]✓ 已就绪！输入查询或输入 exit 退出[/green]")
            console.print()

    def _generate_session_id(self) -> str:
        """生成会话ID"""
        import uuid
        return str(uuid.uuid4())[:8]

    def run_loop(self, debug: bool, live: bool, *, live_ui: str = "classic") -> None:
        """主交互循环，支持动画界面和快捷键。"""
        # 显示欢迎界面
        self._show_welcome()

        # 设置调试模式
        self.debug_mode = debug

        while True:
            try:
                # 使用增强的提示输入（支持快捷键）
                result = self.shortcut_handler.prompt_with_shortcuts("you")

                # 处理快捷键动作
                if result.action:
                    action_result = self.shortcut_handler.execute_shortcut_action(
                        result.action, **result.action_data
                    )

                    if action_result == "exit":
                        break
                    elif action_result == "clear":
                        console.clear()
                        continue
                    elif isinstance(action_result, str) and action_result.startswith("save:"):
                        # 处理保存动作
                        continue
                    elif isinstance(action_result, str) and action_result.startswith("load:"):
                        # 处理加载动作
                        continue
                    # 其他动作继续处理

                user_text = result.text.strip()

                # 处理退出命令
                if user_text.lower() in {"exit", "quit", "/exit", "/quit"}:
                    console.print("\n[bold yellow]再见！[/bold yellow]")
                    break

                # 处理空输入
                if not user_text:
                    continue

                # 执行用户查询
                if live:
                    self._run_with_live(user_text, debug=self.debug_mode, live_ui=live_ui)
                else:
                    self._run_simple(user_text, debug=self.debug_mode)

            except KeyboardInterrupt:
                console.print("\n[bold yellow]再见！[/bold yellow]")
                break
            except Exception as e:
                console.print(f"\n[bold red]错误:[/bold red] {e}")
                if self.debug_mode:
                    import traceback
                    console.print(traceback.format_exc())
                continue

    def _run_with_live(self, user_text: str, debug: bool, *, live_ui: str = "classic") -> None:
        """带 50 行实时面板的执行模式，支持动画和增强确认。"""
        # P0-2：统一入口，UI 可选但事件协议与 AgentLoop 共享，避免双主链路分裂
        if (live_ui or "classic").strip().lower() == "enhanced":
            # P0-2：增强 UI 已迁移至 plugins/ui（可选实现，不污染主链路）
            from clude_code.plugins.ui.enhanced_live_view import EnhancedLiveDisplay

            display = EnhancedLiveDisplay(console, self.cfg)
        else:
            display = LiveDisplay(console, self.cfg)

        def _confirm(msg: str) -> bool:
            """增强的确认提示"""
            try:
                # 显示确认面板
                from rich.panel import Panel
                from rich.text import Text

                confirm_text = Text()
                confirm_text.append("⚠️  确认操作\n\n", style="bold yellow")
                confirm_text.append(msg, style="white")

                panel = Panel(
                    confirm_text,
                    title="需要确认",
                    border_style="yellow",
                    padding=(1, 2)
                )

                console.print(panel)
                console.print()

                return Confirm.ask("[bold cyan]是否继续？[/bold cyan]", default=False)

            except Exception:
                # 降级到简单确认
                return Confirm.ask(msg, default=False)

        with Live(display.render(), console=console, refresh_per_second=12, transient=False) as live_view:
            self._log_turn_start(user_text, debug=True, live=True)
            try:
                def on_event_wrapper(e: dict):
                    display.on_event(e)
                    try:
                        live_view.update(display.render())
                    except Exception:
                        pass

                turn = self.agent.run_turn(user_text, confirm=_confirm, debug=True, on_event=on_event_wrapper)
                self._log_turn_end(turn)
                
                # 结束后固定状态
                if hasattr(display, "active_state"):
                    display.active_state = "DONE"  # type: ignore[attr-defined]
                    display.last_event = "done"  # type: ignore[attr-defined]
                    if hasattr(display, "_push_thought_block"):
                        display._push_thought_block("[done] 本轮结束")  # type: ignore[attr-defined]
                elif hasattr(display, "set_state"):
                    display.set_state("DONE", "本轮结束")  # type: ignore[attr-defined]
                live_view.update(display.render())
                
                self._print_assistant_response(turn, debug=True, show_trace=True)
            except Exception as e:
                self.cli_logger.error(f"AgentLoop 运行异常 (Live): {e}")
                self.cli_logger.exception("AgentLoop 运行异常 (Live)")
                raise typer.Exit(code=1)

    def _run_simple(self, user_text: str, debug: bool) -> None:
        """普通命令行输出模式。"""
        self._log_turn_start(user_text, debug=debug, live=False)
        try:
            def _confirm(msg: str) -> bool:
                return Confirm.ask(msg, default=False)

            turn = self.agent.run_turn(user_text, confirm=_confirm, debug=debug)
            self._log_turn_end(turn)
            self._print_assistant_response(turn, debug=debug, show_trace=not debug)
        except Exception as e:
            self.cli_logger.error(f"AgentLoop 运行异常 (Simple): {e}")
            self.cli_logger.exception("AgentLoop 运行异常 (Simple)")
            raise typer.Exit(code=1)

    def _log_turn_start(self, user_text: str, debug: bool, live: bool) -> None:
        self.cli_logger.log_turn_start(user_text, debug, live)

    def _log_turn_end(self, turn: Any) -> None:
        self.cli_logger.log_turn_end(turn.trace_id, turn.tool_used, len(turn.events))

    def _print_assistant_response(self, turn: Any, debug: bool, show_trace: bool) -> None:
        """打印助手响应，支持动画和面板样式"""
        try:
            from rich.panel import Panel
            from rich.text import Text
            from rich.markdown import Markdown

            # 创建响应内容
            response_content = Text()
            response_content.append(f"assistant (", style="bold magenta")
            response_content.append(f"{turn.trace_id[:8]}", style="dim cyan")
            response_content.append(")\n\n", style="bold magenta")
            response_content.append(turn.assistant_text, style="white")

            # 检查是否启用动画
            if self.config_manager.get_config_value("ui.show_animations"):
                # 使用打字机效果显示响应
                typewriter = TypewriterEffect(console, turn.assistant_text)
                typewriter.set_update_callback(lambda text: self._update_response_display(text, turn.trace_id))

                # 显示响应头
                header_text = Text()
                header_text.append("assistant (", style="bold magenta")
                header_text.append(f"{turn.trace_id[:8]}", style="dim cyan")
                header_text.append(")", style="bold magenta")
                console.print(header_text)

                # 打字机效果显示内容
                typewriter.start()
                typewriter.stop()
                console.print()
            else:
                # 静态显示
                panel = Panel(
                    response_content,
                    title="响应",
                    border_style="magenta",
                    padding=(1, 1)
                )
                console.print(panel)

            # 显示调试信息
            if debug:
                console.print(f"[dim]trace_id: {turn.trace_id}[/dim]")
                if show_trace:
                    self._print_debug_trace(turn)

            console.print()

        except Exception as e:
            # 降级到简单输出
            console.print(f"\n[bold magenta]assistant[/bold magenta] ({turn.trace_id[:8]}...)")
            console.print(turn.assistant_text)
            if debug:
                console.print(f"[dim]trace_id: {turn.trace_id}[/dim]")
                if show_trace:
                    self._print_debug_trace(turn)
            console.print()

    def _update_response_display(self, current_text: str, trace_id: str) -> None:
        """更新响应显示（用于打字机效果）"""
        # 简单的行更新
        console.print(f"\r[white]{current_text}[/white]", end="")

    def _print_debug_trace(self, turn: Any) -> None:
        self.cli_logger.log_debug_trace(turn.events)

