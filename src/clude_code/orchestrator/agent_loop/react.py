from __future__ import annotations

import json
from typing import Any, Callable, TYPE_CHECKING

from clude_code.llm.llama_cpp_http import ChatMessage
from clude_code.orchestrator.state_m import AgentState
from clude_code.tooling.local_tools import ToolResult

if TYPE_CHECKING:
    from .agent_loop import AgentLoop
    from .models import AgentTurn


def execute_react_fallback_loop(
    loop: "AgentLoop",
    trace_id: str,
    keywords: set[str],
    confirm: Callable[[str], bool],
    events: list[dict[str, Any]],
    _ev: Callable[[str, dict[str, Any]], None],
    _llm_chat: Callable[[str, str | None], str],
    _try_parse_tool_call: Callable[[str], dict[str, Any] | None],
    _tool_result_to_message: Callable[[str, ToolResult, set[str] | None], str],
    _set_state: Callable[[AgentState, dict[str, Any] | None], None],
) -> "AgentTurn":
    """执行 ReAct fallback 循环（单级循环，无规划）。"""
    _set_state(AgentState.EXECUTING, {"mode": "react_fallback"})
    tool_used = False

    for iteration in range(20):  # hard stop to avoid infinite loops
        loop.logger.info(f"[bold yellow]→ 第 {iteration + 1} 轮：请求 LLM（消息数={len(loop.messages)}）[/bold yellow]")
        _ev("llm_request", {"messages": len(loop.messages)})

        try:
            assistant = _llm_chat("react_fallback", None)
        except RuntimeError as e:
            error_msg = str(e)
            if "timeout" in error_msg.lower():
                _ev("llm_error", {"error": "timeout", "message": f"LLM 请求超时（{loop.llm.timeout_s}秒）"})
                loop.logger.error(f"[red]LLM 请求超时: {error_msg}[/red]")
                from .models import AgentTurn
                return AgentTurn(
                    assistant_text=f"LLM 请求超时（{loop.llm.timeout_s}秒）。请检查模型服务是否正常运行，或尝试降低 max_tokens（当前: {loop.llm.max_tokens}）。",
                    tool_used=tool_used,
                    trace_id=trace_id,
                    events=events,
                )
            else:
                _ev("llm_error", {"error": "request_failed", "message": error_msg})
                loop.logger.error(f"[red]LLM 请求失败: {error_msg}[/red]")
                from .models import AgentTurn
                return AgentTurn(
                    assistant_text=f"LLM 请求失败: {error_msg}",
                    tool_used=tool_used,
                    trace_id=trace_id,
                    events=events,
                )

        if assistant.count("[") > 50 or assistant.count("{") > 50:
            loop.logger.warning("[red]检测到模型输出异常（复读字符），已强制截断[/red]")
            assistant = "模型输出异常：检测到过多的重复字符，已强制截断。请重新描述你的需求或尝试缩小任务范围。"
            _ev("stuttering_detected", {"length": len(assistant)})

        _ev("llm_response", {"text": assistant[:4000], "truncated": len(assistant) > 4000})
        loop.logger.debug(f"[dim]LLM 响应长度: {len(assistant)} 字符[/dim]")

        tool_call = _try_parse_tool_call(assistant)

        if tool_call is None:
            loop.logger.info("[bold green]✓ LLM 返回最终回复（无工具调用）[/bold green]")
            loop.messages.append(ChatMessage(role="assistant", content=assistant))
            loop.audit.write(trace_id=trace_id, event="assistant_text", data={"text": assistant})
            _ev("final_text", {"text": assistant[:4000], "truncated": len(assistant) > 4000})
            loop._trim_history(max_messages=30)
            from .models import AgentTurn

            return AgentTurn(assistant_text=assistant, tool_used=tool_used, trace_id=trace_id, events=events)

        name = tool_call["tool"]
        args = tool_call["args"]
        args_summary = loop._format_args_summary(name, args)
        loop.logger.info(f"[bold blue]🔧 解析到工具调用: {name}[/bold blue] [轮次] {iteration + 1}/20 [参数] {args_summary}")
        loop.file_only_logger.info(f"工具调用详情 [iteration={iteration + 1}] [tool={name}] [args={json.dumps(args, ensure_ascii=False)}]")
        _ev("tool_call_parsed", {"tool": name, "args": args})

        clean_assistant = json.dumps(tool_call, ensure_ascii=False)
        loop.messages.append(ChatMessage(role="assistant", content=clean_assistant))
        _ev("assistant_tool_call_recorded", {"tool": name})
        loop._trim_history(max_messages=30)

        result = loop._run_tool_lifecycle(name, args, trace_id, confirm, _ev)
        tool_used = True

        _ev("tool_result", {"tool": name, "ok": result.ok, "error": result.error, "payload": result.payload})

        result_msg = _tool_result_to_message(name, result, keywords=keywords)
        loop.messages.append(ChatMessage(role="user", content=result_msg))
        loop.logger.debug(f"[dim]工具结果已回喂[/dim] [工具] {name}")
        loop.file_only_logger.debug(f"工具结果回喂 [tool={name}] [len={len(result_msg)}]")
        _ev("tool_result_fed_back", {"tool": name})
        loop._trim_history(max_messages=30)

    loop.logger.warning("[red]⚠ 达到最大工具调用次数（20），停止以避免死循环[/red]")
    _ev("stop_reason", {"reason": "max_tool_calls_reached", "limit": 20})
    from .models import AgentTurn

    return AgentTurn(
        assistant_text="达到本轮最大工具调用次数（20），已停止以避免死循环。请缩小任务或提供更多约束/入口文件。",
        tool_used=tool_used,
        trace_id=trace_id,
        events=events,
    )


