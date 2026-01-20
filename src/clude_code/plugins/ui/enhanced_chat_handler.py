"""
增强的聊天处理器，支持异步操作和细粒度进度指示
"""
from __future__ import annotations

import asyncio
from typing import Any, Optional
import time

from rich.console import Console
from rich.live import Live
from rich.prompt import Confirm, Prompt

from clude_code.config.config import CludeConfig
from clude_code.core.async_manager import AsyncTaskManager, get_async_manager
from clude_code.llm.streaming_client import StreamingLLMClient, CachedStreamingLLMClient
from clude_code.plugins.ui.enhanced_live_view import EnhancedLiveDisplay, SimpleProgressDisplay, TaskType
from clude_code.orchestrator.agent_loop import AgentLoop
from clude_code.llm.llama_cpp_http import ChatMessage
from clude_code.tooling.local_tools import ToolResult


class EnhancedAgentLoop(AgentLoop):
    """增强的 AgentLoop，支持异步操作和细粒度进度指示"""
    
    def __init__(self, cfg: CludeConfig) -> None:
        super().__init__(cfg)
        self.async_manager = get_async_manager(cfg.workspace_root)
        self.streaming_client = CachedStreamingLLMClient(
            workspace_root=cfg.workspace_root,
            base_url=cfg.llm.base_url,
            api_mode=cfg.llm.api_mode,
            model=cfg.llm.model,
            temperature=cfg.llm.temperature,
            max_tokens=cfg.llm.max_tokens,
            timeout_s=cfg.llm.timeout_s,
            cache_size=50  # 缓存50个响应
        )
        self.enhanced_display: Optional[EnhancedLiveDisplay] = None
        self.simple_display: Optional[SimpleProgressDisplay] = None
    
    def set_enhanced_display(self, display: EnhancedLiveDisplay) -> None:
        """设置增强显示组件"""
        self.enhanced_display = display
    
    def set_simple_display(self, display: SimpleProgressDisplay) -> None:
        """设置简单显示组件"""
        self.simple_display = display
    
    async def run_turn_async(
        self,
        user_text: str,
        *,
        confirm: callable,
        debug: bool = False,
        on_event: Optional[callable] = None,
    ) -> Any:
        """异步执行一轮 Agent 对话循环"""
        # 创建任务ID
        turn_id = f"turn_{int(time.time())}"
        
        # 添加主任务
        await self.async_manager.create_task(
            task_id=turn_id,
            coro=self._run_turn_core_async(user_text, confirm, debug, on_event, turn_id),
            progress_callback=self._on_task_progress
        )
        
        # 等待任务完成
        result = await self.async_manager.wait_for_task(turn_id)
        return result
    
    async def _run_turn_core_async(
        self,
        user_text: str,
        confirm: callable,
        debug: bool,
        on_event: Optional[callable],
        turn_id: str
    ) -> Any:
        """异步执行核心逻辑"""
        # 提取关键词
        keywords = self._extract_keywords(user_text)
        
        # 更新状态
        self._update_state("INTAKE", "处理用户输入")
        
        # 添加用户消息
        self.messages.append(ChatMessage(role="user", content=user_text))
        if on_event:
            on_event({"event": "user_message", "data": {"text": user_text}})
        
        # 执行工具调用循环
        for iteration in range(20):  # 最大20次迭代
            # 更新状态
            self._update_state("THINKING", f"思考中 (轮次 {iteration + 1})")
            
            # 创建 LLM 请求任务
            llm_task_id = f"llm_{turn_id}_{iteration}"
            await self.async_manager.create_task(
                task_id=llm_task_id,
                coro=self._llm_request_async(keywords, on_event, llm_task_id),
                progress_callback=self._on_task_progress
            )
            
            # 等待 LLM 响应
            response = await self.async_manager.wait_for_task(llm_task_id)
            
            # 检查是否有工具调用
            tool_call = self._try_parse_tool_call(response)
            if not tool_call:
                # 没有工具调用，返回最终响应
                self._update_state("DONE", "完成")
                # 创建一个简单的返回对象
                from types import SimpleNamespace
                return SimpleNamespace(
                    trace_id=turn_id,
                    final_response=response,
                    tool_used=False,
                    events=[]
                )
            
            # 执行工具调用
            tool_name = tool_call["tool"]
            tool_args = tool_call["args"]
            
            # 更新状态
            self._update_state("EXECUTING", f"执行工具: {tool_name}")
            
            # 创建工具执行任务
            tool_task_id = f"tool_{turn_id}_{iteration}"
            await self.async_manager.create_task(
                task_id=tool_task_id,
                coro=self._execute_tool_async(tool_name, tool_args, confirm, on_event),
                progress_callback=self._on_task_progress
            )
            
            # 等待工具执行完成
            tool_result = await self.async_manager.wait_for_task(tool_task_id)
            
            # 将结果回喂给 LLM
            result_msg = _tool_result_to_message(tool_name, tool_result, keywords)
            self.messages.append(ChatMessage(role="user", content=result_msg))
            
            if on_event:
                on_event({
                    "event": "tool_result",
                    "data": {
                        "tool": tool_name,
                        "ok": tool_result.ok,
                        "error": tool_result.error,
                        "payload": tool_result.payload
                    }
                })
        
        # 达到最大迭代次数
        self._update_state("DONE", "达到最大迭代次数")
        from types import SimpleNamespace
        return SimpleNamespace(
            trace_id=turn_id,
            final_response="达到最大迭代次数，请简化任务或重试。",
            tool_used=True,
            events=[]
        )
    
    async def _llm_request_async(
        self,
        keywords: set[str],
        on_event: Optional[callable],
        task_id: str
    ) -> str:
        """异步 LLM 请求"""
        # 通知开始 LLM 请求
        if self.enhanced_display:
            self.enhanced_display.add_task(
                task_type=TaskType.LLM_REQUEST,
                description="LLM 请求处理",
                estimated_duration=10.0
            )
        elif self.simple_display:
            self.simple_display.add_task(
                task_type=TaskType.LLM_REQUEST,
                description="LLM 请求处理",
                estimated_duration=10.0
            )
        
        if on_event:
            on_event({"event": "llm_request", "data": {"messages": len(self.messages)}})
        
        # 流式处理响应
        accumulated_response = ""
        
        async def on_progress(content: str, progress: float):
            nonlocal accumulated_response
            accumulated_response += content
            
            # 更新进度
            if self.enhanced_display:
                # 找到活跃的 LLM 任务并更新
                llm_tasks = [
                    t for t in self.enhanced_display.active_tasks.values()
                    if t.task_type == TaskType.LLM_REQUEST
                ]
                if llm_tasks:
                    self.enhanced_display.update_task(
                        llm_tasks[-1].task_id,
                        progress=progress,
                        details={"generated_length": len(accumulated_response)}
                    )
            elif self.simple_display:
                # 简单进度显示
                self.simple_display.update_task(
                    "llm_request",  # 使用固定的任务ID
                    progress=progress,
                    message=f"已生成 {len(accumulated_response)} 字符"
                )
        
        # 发送流式请求
        async for chunk in self.streaming_client.chat_stream(
            self.messages,
            on_progress=on_progress,
            task_id=task_id
        ):
            if chunk.done:
                break
        
        # 完成 LLM 任务
        if self.enhanced_display:
            llm_tasks = [
                t for t in self.enhanced_display.active_tasks.values()
                if t.task_type == TaskType.LLM_REQUEST
            ]
            if llm_tasks:
                self.enhanced_display.complete_task(llm_tasks[-1].task_id)
        elif self.simple_display:
            self.simple_display.complete_task("llm_request")
        
        if on_event:
            on_event({
                "event": "llm_response",
                "data": {"text": accumulated_response}
            })
        
        return accumulated_response
    
    async def _execute_tool_async(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        confirm: callable,
        on_event: Optional[callable]
    ) -> ToolResult:
        """异步执行工具"""
        # 确定任务类型和描述
        task_type = TaskType.FILE_READ
        description = f"执行工具: {tool_name}"
        estimated_duration = 2.0
        
        if tool_name == "read_file":
            task_type = TaskType.FILE_READ
            path = tool_args.get("path", "")
            description = f"读取文件: {path}"
        elif tool_name == "write_file":
            task_type = TaskType.FILE_WRITE
            path = tool_args.get("path", "")
            description = f"写入文件: {path}"
        elif tool_name == "grep":
            task_type = TaskType.SEARCH
            pattern = tool_args.get("pattern", "")
            description = f"搜索: {pattern}"
        elif tool_name == "run_cmd":
            task_type = TaskType.COMMAND_EXEC
            command = tool_args.get("command", "")
            description = f"执行命令: {command}"
        
        # 添加任务
        task_id = None
        if self.enhanced_display:
            task_id = self.enhanced_display.add_task(
                task_type=task_type,
                description=description,
                estimated_duration=estimated_duration
            )
        elif self.simple_display:
            task_id = self.simple_display.add_task(
                task_type=task_type,
                description=description,
                estimated_duration=estimated_duration
            )
        
        # 执行工具
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._run_tool_sync(tool_name, tool_args, confirm)
            )
            
            # 完成任务
            if self.enhanced_display and task_id:
                self.enhanced_display.complete_task(task_id)
            elif self.simple_display and task_id:
                self.simple_display.complete_task(task_id)
            
            return result
        except Exception as e:
            # 任务失败
            if self.enhanced_display and task_id:
                self.enhanced_display.fail_task(task_id, str(e))
            elif self.simple_display and task_id:
                self.simple_display.fail_task(task_id, str(e))
            
            return ToolResult(
                ok=False,
                error={"code": "EXECUTION_ERROR", "message": str(e)}
            )
    
    def _run_tool_sync(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        confirm: callable
    ) -> ToolResult:
        """同步执行工具（在 executor 中运行）"""
        # 这里调用原有的工具执行逻辑
        return self._run_tool_lifecycle(tool_name, tool_args, "trace_id", confirm, lambda e, d: None)
    
    def _update_state(self, state: str, operation: str) -> None:
        """更新状态"""
        if self.enhanced_display:
            self.enhanced_display.set_state(state, operation)
        elif self.simple_display:
            self.simple_display.print_event(f"状态更新: {state} - {operation}")
    
    def _on_task_progress(self, task_progress) -> None:
        """任务进度回调"""
        # 这里可以添加额外的进度处理逻辑
        pass
    
    def _extract_keywords(self, text: str) -> set[str]:
        """提取关键词"""
        # 简单的关键词提取实现
        import re
        words = re.findall(r'\b\w+\b', text.lower())
        # 过滤掉短词和常见词
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'must', 'can', 'this', 'that', 'these', 'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they', 'me', 'him', 'her', 'us', 'them', 'my', 'your', 'his', 'its', 'our', 'their'}
        keywords = {w for w in words if len(w) >= 3 and w not in stop_words}
        return keywords


class EnhancedChatHandler:
    """
    增强的聊天处理器，支持异步操作和细粒度进度指示
    """
    def __init__(self, cfg: CludeConfig, logger: Any, file_only_logger: Any):
        self.cfg = cfg
        self.logger = logger
        self.file_only_logger = file_only_logger
        self.agent = EnhancedAgentLoop(cfg)

    def select_model_interactively(self) -> None:
        """调用公共工具进行交互式模型选择。"""
        from clude_code.cli.utils import select_model_interactively
        select_model_interactively(self.cfg, self.logger)

    def run_loop(self, debug: bool, live: bool) -> None:
        """主交互循环。"""
        self.logger.info("[bold]进入 clude chat (增强模式)[/bold]")
        self.logger.info("- 输入 `exit` 退出")
        self.logger.info("- 输入 `config` 运行配置向导")
        self.logger.info("- 输入 `stats` 查看性能统计")

        while True:
            user_text = Prompt.ask("you")
            if user_text.strip().lower() in {"exit", "quit"}:
                self.logger.info("bye")
                break
            
            if user_text.strip().lower() == "config":
                from clude_code.config.config_wizard import run_config_wizard
                try:
                    new_config = run_config_wizard(self.cfg.workspace_root)
                    # 更新当前配置
                    self.cfg = new_config
                    self.agent = EnhancedAgentLoop(self.cfg)
                    self.logger.info("[green]配置已更新[/green]")
                except Exception as e:
                    self.logger.error(f"配置更新失败: {e}")
                continue
            
            if user_text.strip().lower() == "stats":
                self._show_stats()
                continue

            if live:
                asyncio.run(self._run_with_live_async(user_text, debug=True))
            else:
                asyncio.run(self._run_simple_async(user_text, debug=debug))

    async def _run_with_live_async(self, user_text: str, debug: bool) -> None:
        """带增强实时面板的异步执行模式。"""
        console = Console()
        display = EnhancedLiveDisplay(console, self.cfg)
        self.agent.set_enhanced_display(display)

        def _confirm(msg: str) -> bool:
            return Confirm.ask(msg, default=False)

        with Live(display.render(), console=console, refresh_per_second=4, transient=False) as live_view:
            self._log_turn_start(user_text, debug=True, live=True)
            try:
                def on_event_wrapper(e: dict):
                    display.on_event(e)
                    try:
                        live_view.update(display.render())
                    except Exception:
                        pass

                turn = await self.agent.run_turn_async(user_text, confirm=_confirm, debug=True, on_event=on_event_wrapper)
                self._log_turn_end(turn)
                
                # 结束后固定状态
                display.set_state("DONE", "本轮完成")
                live_view.update(display.render())
                
                self._print_assistant_response(turn, debug=True, show_trace=True)
            except Exception as e:
                self.logger.error(f"AgentLoop 运行异常 (Live): {e}", exc_info=True)
                self.file_only_logger.exception("AgentLoop 运行异常 (Live)")
                console.print(f"[red]错误: {e}[/red]")

    async def _run_simple_async(self, user_text: str, debug: bool) -> None:
        """普通命令行输出模式（异步）。"""
        console = Console()
        display = SimpleProgressDisplay(console)
        self.agent.set_simple_display(display)

        def _confirm(msg: str) -> bool:
            return Confirm.ask(msg, default=False)

        self._log_turn_start(user_text, debug=debug, live=False)
        try:
            def on_event_wrapper(e: dict):
                display.print_event(f"事件: {e.get('event', 'unknown')}")

            turn = await self.agent.run_turn_async(user_text, confirm=_confirm, debug=debug, on_event=on_event_wrapper)
            self._log_turn_end(turn)
            self._print_assistant_response(turn, debug=debug, show_trace=not debug)
        except Exception as e:
            self.logger.error(f"AgentLoop 运行异常 (Simple): {e}", exc_info=True)
            self.file_only_logger.exception("AgentLoop 运行异常 (Simple)")
            console.print(f"[red]错误: {e}[/red]")

    def _log_turn_start(self, user_text: str, debug: bool, live: bool) -> None:
        self.file_only_logger.info(
            f"Turn Start (Async) - input: {user_text[:100]}..., debug={debug}, live={live}, "
            f"model={self.cfg.llm.model}"
        )

    def _log_turn_end(self, turn: Any) -> None:
        self.file_only_logger.info(
            f"Turn End (Async) - trace_id={turn.trace_id}, tool_used={turn.tool_used}, events={len(turn.events)}"
        )

    def _print_assistant_response(self, turn: Any, debug: bool, show_trace: bool) -> None:
        """打印助手响应。"""
        console = Console()
        console.print(f"\n[bold]助手:[/bold] {turn.final_response}")
        
        if show_trace and hasattr(turn, 'events') and turn.events:
            console.print("\n[bold dim]执行轨迹:[/bold dim]")
            for event in turn.events[-5:]:  # 只显示最后5个事件
                console.print(f"  - {event.get('event', 'unknown')}: {event.get('data', {})}")
    
    def _show_stats(self) -> None:
        """显示性能统计"""
        console = Console()
        
        # LLM 客户端统计
        llm_stats = self.agent.streaming_client.get_stats()
        console.print("\n[bold]LLM 客户端统计:[/bold]")
        stats_table = Table(show_header=True, box=None)
        stats_table.add_column("指标", style="bold")
        stats_table.add_column("值", justify="right")
        
        stats_table.add_row("请求次数", str(llm_stats["request_count"]))
        stats_table.add_row("总 Token 数", str(llm_stats["total_tokens"]))
        stats_table.add_row("总耗时", f"{llm_stats['total_time']:.2f}s")
        stats_table.add_row("平均耗时/请求", f"{llm_stats['avg_time_per_request']:.2f}s")
        stats_table.add_row("平均 Token/请求", str(int(llm_stats['avg_tokens_per_request'])))
        
        console.print(stats_table)
        
        # 缓存统计
        cache_stats = self.agent.streaming_client.get_cache_stats()
        console.print("\n[bold]缓存统计:[/bold]")
        cache_table = Table(show_header=True, box=None)
        cache_table.add_column("指标", style="bold")
        cache_table.add_column("值", justify="right")
        
        cache_table.add_row("缓存大小", f"{cache_stats['cache_size']}/{cache_stats['max_cache_size']}")
        cache_table.add_row("缓存命中", str(cache_stats['cache_hits']))
        cache_table.add_row("缓存未命中", str(cache_stats['cache_misses']))
        cache_table.add_row("命中率", f"{cache_stats['hit_rate']:.2%}")
        
        console.print(cache_table)
        
        # 异步任务管理器统计
        all_tasks = self.agent.async_manager.get_all_tasks()
        active_tasks = [t for t in all_tasks.values() if t.status.value == "running"]
        completed_tasks = [t for t in all_tasks.values() if t.status.value == "completed"]
        failed_tasks = [t for t in all_tasks.values() if t.status.value == "failed"]
        
        console.print("\n[bold]任务统计:[/bold]")
        task_table = Table(show_header=True, box=None)
        task_table.add_column("状态", style="bold")
        task_table.add_column("数量", justify="right")
        
        task_table.add_row("活跃任务", str(len(active_tasks)))
        task_table.add_row("已完成任务", str(len(completed_tasks)))
        task_table.add_row("失败任务", str(len(failed_tasks)))
        task_table.add_row("总任务数", str(len(all_tasks)))
        
        console.print(task_table)


def _tool_result_to_message(name: str, tr: ToolResult, keywords: set[str] | None = None) -> str:
    """
    将工具执行结果转换为发送给 LLM 的结构化消息。
    
    本函数采用业界最佳实践：只保留决策关键字段和引用，避免将完整 payload 回喂给模型，
    从而减少 Token 消耗并提升模型聚焦度。
    
    参数:
        name: 工具名称（如 "read_file", "grep"）
        tr: 工具执行结果（ToolResult 对象）
        keywords: 可选的关键词集合，用于语义窗口采样（优先保留包含关键词的代码片段）
    
    返回:
        格式化的字符串消息，将被作为 "user" 角色的消息发送给 LLM
    """
    from clude_code.tooling.feedback import format_feedback_message
    return format_feedback_message(name, tr, keywords=keywords)