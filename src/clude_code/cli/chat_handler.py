import logging
import typer
from rich.console import Console
from rich.live import Live
from rich.prompt import Confirm, Prompt

from clude_code.config import CludeConfig
from clude_code.orchestrator.agent_loop import AgentLoop
from clude_code.cli.live_view import LiveDisplay
from clude_code.cli.utils import select_model_interactively

console = Console()

class ChatHandler:
    """
    负责处理交互式聊天循环与 AgentLoop 的集成。
    """
    def __init__(self, cfg: CludeConfig, logger: logging.Logger, file_only_logger: logging.Logger):
        self.cfg = cfg
        self.logger = logger
        self.file_only_logger = file_only_logger
        self.agent = AgentLoop(cfg)

    def select_model_interactively(self) -> None:
        """调用公共工具进行交互式模型选择。"""
        select_model_interactively(self.cfg, self.logger)

    def run_loop(self, debug: bool, live: bool) -> None:
        """主交互循环。"""
        self.logger.info("[bold]进入 clude chat[/bold]")
        self.logger.info("- 输入 `exit` 退出")

        while True:
            user_text = typer.prompt("you")
            if user_text.strip().lower() in {"exit", "quit"}:
                self.logger.info("bye")
                break

            if live:
                self._run_with_live(user_text, debug=True)
            else:
                self._run_simple(user_text, debug=debug)

    def _run_with_live(self, user_text: str, debug: bool) -> None:
        """带 50 行实时面板的执行模式。"""
        display = LiveDisplay(console, self.cfg)

        def _confirm(msg: str) -> bool:
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
                display.active_state = "DONE"
                display.last_event = "done"
                display._push_thought_block("[done] 本轮结束")
                live_view.update(display.render())
                
                self._print_assistant_response(turn, debug=True, show_trace=True)
            except Exception:
                self.file_only_logger.exception("AgentLoop 运行异常 (Live)", exc_info=True)
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
        except Exception:
            self.file_only_logger.exception("AgentLoop 运行异常 (Simple)", exc_info=True)
            raise typer.Exit(code=1)

    def _log_turn_start(self, user_text: str, debug: bool, live: bool) -> None:
        self.file_only_logger.info(
            f"Turn Start - input: {user_text[:100]}..., debug={debug}, live={live}, "
            f"model={self.cfg.llm.model}"
        )

    def _log_turn_end(self, turn: Any) -> None:
        self.file_only_logger.info(
            f"Turn End - trace_id={turn.trace_id}, tool_used={turn.tool_used}, events={len(turn.events)}"
        )

    def _print_assistant_response(self, turn: Any, debug: bool, show_trace: bool) -> None:
        self.logger.info("\n[bold]assistant[/bold]")
        self.logger.info(turn.assistant_text)
        if debug:
            self.logger.debug(f"trace_id={turn.trace_id}")
            if show_trace:
                self._print_debug_trace(turn)
        self.logger.info("")

    def _print_debug_trace(self, turn: Any) -> None:
        self.logger.debug("--- agent 执行轨迹 ---")
        for e in turn.events:
            step = e.get("step")
            ev = e.get("event")
            data = e.get("data", {})
            if ev in {"llm_response", "final_text"}:
                txt = str(data.get("text", ""))
                self.logger.debug(f"{step}. {ev} {txt[:120]}...")
            elif ev == "tool_call_parsed":
                self.logger.debug(f"{step}. tool {data.get('tool')} args={data.get('args')}")
            else:
                self.logger.debug(f"{step}. {ev}")

