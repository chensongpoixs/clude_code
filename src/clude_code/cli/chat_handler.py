from typing import Any
import json
import re
from pathlib import Path
import typer
from rich.console import Console
from rich.live import Live
from rich.prompt import Confirm

from clude_code.config.config import CludeConfig
from clude_code.orchestrator.agent_loop import AgentLoop
from clude_code.cli.live_view import LiveDisplay
from clude_code.cli.utils import select_model_interactively
from clude_code.cli.theme import CLAUDE_THEME, create_welcome_text, create_status_bar, create_ready_message
from clude_code.cli.animations import AnimatedWelcome, TypewriterEffect, FadeEffect
from clude_code.cli.shortcuts import ShortcutHandler, ShortcutAction, PromptResult
from clude_code.config import get_config_manager
from clude_code.cli.cli_logging import get_cli_logger
from clude_code.cli.slash_commands import SlashContext, handle_slash_command
from clude_code.cli.session_store import save_session
from clude_code.cli.custom_commands import load_custom_commands, expand_custom_command
from clude_code.llm.image_utils import load_image_from_path, load_image_from_url

# 使用主题化的控制台
console = Console(theme=CLAUDE_THEME)

class ChatHandler:
    """
    负责处理交互式聊天循环与 AgentLoop 的集成。
    支持动画界面、快捷键和配置管理。
    """
    def __init__(self, cfg: CludeConfig, *, session_id: str | None = None, history: list[Any] | None = None):
        self.cfg = cfg
        self.agent = AgentLoop(cfg, session_id=session_id)
        if history:
            # 只追加 user/assistant 历史，system 由本轮最新 repo map/CLUDE.md 生成
            self.agent.messages.extend(history)  # type: ignore[arg-type]

        # 初始化统一的日志系统
        self.cli_logger = get_cli_logger()

        # 初始化新功能组件
        self.config_manager = get_config_manager()
        self.shortcut_handler = ShortcutHandler(console)
        self.animated_welcome = AnimatedWelcome(console)

        # 会话状态
        self.session_id = self._generate_session_id()
        self.debug_mode = False
        self._last_trace_id: str | None = None
        self._last_user_text: str | None = None

        # 自定义命令（.clude/commands/*.md）
        self._custom_commands = load_custom_commands(self.cfg.workspace_root)
        
        # 图片缓存（用于 /image 命令预加载）
        self._pending_images: list[dict[str, Any]] = []
        self._pending_image_paths: list[str] = []

    def _extract_images_from_input(self, user_input: str) -> tuple[str, list[dict[str, Any]], list[str]]:
        """
        从用户输入中提取图片路径/URL。
        
        支持格式：
        - @image:path/to/image.png
        - @image:https://example.com/image.png
        
        Returns:
            (clean_text, images, image_paths)
        """
        images: list[dict[str, Any]] = []
        image_paths: list[str] = []
        clean_text = user_input
        
        # 匹配 @image:path 模式
        pattern = r'@image:([^\s]+)'
        matches = re.findall(pattern, user_input)
        
        for path_or_url in matches:
            # 移除匹配的文本
            clean_text = clean_text.replace(f'@image:{path_or_url}', '')
            
            if path_or_url.startswith(('http://', 'https://')):
                # URL
                img = load_image_from_url(path_or_url)
                if img:
                    images.append(img)
                    image_paths.append(path_or_url)
                    console.print(f"[dim]✓ 已加载图片: {path_or_url[:50]}...[/dim]")
                else:
                    console.print(f"[yellow]⚠ 无法加载图片: {path_or_url}[/yellow]")
            else:
                # 本地路径
                img = load_image_from_path(path_or_url)
                if img:
                    images.append(img)
                    image_paths.append(path_or_url)
                    console.print(f"[dim]✓ 已加载图片: {path_or_url}[/dim]")
                else:
                    console.print(f"[yellow]⚠ 无法加载图片: {path_or_url}[/yellow]")
        
        # 合并预加载的图片（来自 /image 命令，存储在 agent 中）
        pending = getattr(self.agent, "_pending_images", None) or self._pending_images
        pending_paths = getattr(self.agent, "_pending_image_paths", None) or self._pending_image_paths
        if pending:
            images.extend(pending)
            image_paths.extend(pending_paths)
            console.print(f"[dim]✓ 已附加 {len(pending)} 张预加载图片[/dim]")
            if hasattr(self.agent, "_pending_images"):
                self.agent._pending_images = []
            if hasattr(self.agent, "_pending_image_paths"):
                self.agent._pending_image_paths = []
            self._pending_images.clear()
            self._pending_image_paths.clear()
        
        return clean_text.strip(), images, image_paths

    def select_model_interactively(self) -> None:
        """调用公共工具进行交互式模型选择，并同步更新 AgentLoop。"""
        old_model = self.cfg.llm.model
        select_model_interactively(self.cfg, self.cli_logger.console)
        new_model = self.cfg.llm.model
        
        # 如果模型发生变化，同步更新 AgentLoop 的 LLM 客户端
        if new_model != old_model and hasattr(self.agent, 'switch_model'):
            self.agent.switch_model(new_model, validate=False)
        elif new_model != old_model and hasattr(self.agent, 'llm'):
            # 降级：直接更新 llm.model
            self.agent.llm.model = new_model

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

        # OpenCode 风格 TUI：直接进入 Textual UI（自身包含输入框与历史滚动）
        if live and (live_ui or "classic").strip().lower() in {"opencode", "textual"}:
            try:
                from clude_code.plugins.ui.opencode_tui import run_opencode_tui
            except Exception:
                console.print(
                    "[red]未安装 Textual，无法启用 opencode UI。[/red]\n"
                    "请安装可选依赖：\n"
                    "[dim]pip install -e \".[ui]\"[/dim]"
                )
                # 降级回原 live 逻辑
            else:
                def _run_turn(
                    text: str,
                    confirm: Any,
                    on_event: Any,
                ) -> None:
                    turn = self.agent.run_turn(text, confirm=confirm, debug=self.debug_mode, on_event=on_event)
                    self._last_trace_id = getattr(turn, "trace_id", None)
                    try:
                        save_session(
                            workspace_root=self.cfg.workspace_root,
                            session_id=self.agent.session_id,
                            messages=self.agent.messages,
                            last_trace_id=self._last_trace_id,
                        )
                    except Exception:
                        pass

                run_opencode_tui(cfg=self.cfg, agent=self.agent, debug=self.debug_mode, run_turn=_run_turn)
                return

        while True:
            try:
                # 每轮都做一次轻量刷新（支持用户新增/修改 .clude/commands/*.md 后生效）
                self._custom_commands = load_custom_commands(self.cfg.workspace_root)

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
                self._last_user_text = user_text

                # 先尝试自定义命令展开（对标 Claude Code 的自定义 commands）
                expanded = expand_custom_command(commands=self._custom_commands, user_text=user_text)
                policy_overrides: dict[str, Any] = {}
                if expanded is not None:
                    if expanded.errors:
                        for err in expanded.errors:
                            console.print(f"[red]{err}[/red]")
                        continue
                    console.print(f"[dim]执行自定义命令: /{expanded.command.name} ({Path(expanded.command.path).name})[/dim]")
                    policy_overrides = expanded.policy_overrides or {}
                    user_text = expanded.prompt

                # Claude Code 风格：Slash Commands（本地命令层，不走 LLM）
                if user_text.startswith("/"):
                    ctx = SlashContext(
                        console=console,
                        cfg=self.cfg,
                        agent=self.agent,
                        debug=self.debug_mode,
                        last_trace_id=self._last_trace_id,
                        last_user_text=self._last_user_text,
                    )
                    try:
                        if handle_slash_command(ctx, user_text):
                            continue
                    except SystemExit:
                        break

                # 处理退出命令
                if user_text.lower() in {"exit", "quit", "/exit", "/quit"}:
                    console.print("\n[bold yellow]再见！[/bold yellow]")
                    break

                # 处理空输入
                if not user_text:
                    continue

                # 执行用户查询
                old_policy: dict[str, Any] = {}
                try:
                    if policy_overrides:
                        # 命令级权限声明：仅对本次执行生效（执行后恢复）
                        p = self.cfg.policy
                        for k, v in policy_overrides.items():
                            old_policy[k] = getattr(p, k, None)
                            setattr(p, k, v)

                    # 提取图片（@image:path 语法）
                    user_text, images, image_paths = self._extract_images_from_input(user_text)
                    
                    if live:
                        self._run_with_live(user_text, debug=self.debug_mode, live_ui=live_ui, images=images, image_paths=image_paths)
                    else:
                        self._run_simple(user_text, debug=self.debug_mode, images=images, image_paths=image_paths)
                finally:
                    if old_policy:
                        p = self.cfg.policy
                        for k, v in old_policy.items():
                            setattr(p, k, v)

            except KeyboardInterrupt:
                console.print("\n[bold yellow]再见！[/bold yellow]")
                break
            except Exception as e:
                console.print(f"\n[bold red]错误:[/bold red] {e}")
                if self.debug_mode:
                    import traceback
                    console.print(traceback.format_exc())
                continue

    def run_print(self, prompt: str, *, debug: bool, output_format: str = "text", yes: bool = False) -> None:
        """
        非交互（Print）模式：执行一次 prompt 后退出。
        对标 Claude Code 的 `-p/--print` 用法。
        """
        prompt = (prompt or "").strip()
        if not prompt:
            raise typer.BadParameter("--print 模式需要提供 prompt 文本（例如：clude chat -p \"解释这个项目\"）")

        def _confirm(_msg: str) -> bool:
            # 非交互模式默认拒绝；用户显式 --yes 才自动同意
            return bool(yes)

        # 不显示欢迎/动画，直接执行
        self.debug_mode = debug
        turn = self.agent.run_turn(prompt, confirm=_confirm, debug=debug)
        self._last_trace_id = getattr(turn, "trace_id", None)
        try:
            save_session(
                workspace_root=self.cfg.workspace_root,
                session_id=self.agent.session_id,
                messages=self.agent.messages,
                last_trace_id=self._last_trace_id,
            )
        except Exception:
            pass

        fmt = (output_format or "text").strip().lower()
        if fmt == "json":
            payload = {
                "ok": True,
                "trace_id": getattr(turn, "trace_id", None),
                "assistant_text": getattr(turn, "assistant_text", ""),
                "tool_used": bool(getattr(turn, "tool_used", False)),
                "did_modify_code": bool(getattr(turn, "did_modify_code", False)),
                "events_count": len(getattr(turn, "events", []) or []),
            }
            typer.echo(json.dumps(payload, ensure_ascii=False))
        else:
            typer.echo(getattr(turn, "assistant_text", ""))

    def _run_with_live(
        self,
        user_text: str,
        debug: bool,
        *,
        live_ui: str = "classic",
        images: list[dict[str, Any]] | None = None,
        image_paths: list[str] | None = None,
    ) -> None:
        """带 50 行实时面板的执行模式，支持动画和增强确认。"""
        # P0-2：统一入口，UI 可选但事件协议与 AgentLoop 共享，避免双主链路分裂
        ui_mode = (live_ui or "classic").strip().lower()

        # opencode/textual 模式在 run_loop 已接管（包含输入框与滚动），此处不再处理
        if ui_mode in {"opencode", "textual"}:
            ui_mode = "enhanced"

        if ui_mode == "enhanced":
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

                turn = self.agent.run_turn(
                    user_text,
                    confirm=_confirm,
                    debug=True,
                    on_event=on_event_wrapper,
                    images=images,
                    image_paths=image_paths,
                )
                self._last_trace_id = getattr(turn, "trace_id", None)
                self._log_turn_end(turn)
                try:
                    save_session(
                        workspace_root=self.cfg.workspace_root,
                        session_id=self.agent.session_id,
                        messages=self.agent.messages,
                        last_trace_id=self._last_trace_id,
                    )
                except Exception:
                    pass
                
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

    def _run_simple(
        self,
        user_text: str,
        debug: bool,
        *,
        images: list[dict[str, Any]] | None = None,
        image_paths: list[str] | None = None,
    ) -> None:
        """普通命令行输出模式。"""
        self._log_turn_start(user_text, debug=debug, live=False)
        try:
            def _confirm(msg: str) -> bool:
                return Confirm.ask(msg, default=False)

            turn = self.agent.run_turn(
                user_text,
                confirm=_confirm,
                debug=debug,
                images=images,
                image_paths=image_paths,
            )
            self._last_trace_id = getattr(turn, "trace_id", None)
            self._log_turn_end(turn)
            try:
                save_session(
                    workspace_root=self.cfg.workspace_root,
                    session_id=self.agent.session_id,
                    messages=self.agent.messages,
                    last_trace_id=self._last_trace_id,
                )
            except Exception:
                pass
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

