from __future__ import annotations

import json
from typing import Any, Callable, TYPE_CHECKING

from clude_code.llm.llama_cpp_http import ChatMessage
from clude_code.tooling.local_tools import ToolResult
from clude_code.orchestrator.state_m import AgentState
from clude_code.orchestrator.planner import Plan

if TYPE_CHECKING:
    from .agent_loop import AgentLoop
    from .models import AgentTurn


def check_step_dependencies(
    loop: "AgentLoop",
    step,
    plan: Plan,
    trace_id: str,
    _ev: Callable[[str, dict[str, Any]], None],
) -> list[str]:
    """检查步骤依赖是否满足，如果不满足则标记为 blocked。"""
    completed_ids = {s.id for s in plan.steps if s.status == "done"}
    unmet_deps = [dep for dep in step.dependencies if dep not in completed_ids]
    if unmet_deps:
        loop.logger.warning(f"[yellow]⚠ 步骤 {step.id} 有未满足的依赖: {unmet_deps}，跳过并标记为 blocked[/yellow]")
        step.status = "blocked"
        loop.audit.write(trace_id=trace_id, event="plan_step_blocked", data={"step_id": step.id, "unmet_deps": unmet_deps})
        _ev("plan_step_blocked", {"step_id": step.id, "unmet_deps": unmet_deps})
    return unmet_deps


def handle_tool_call_in_step(
    loop: "AgentLoop",
    name: str,
    args: dict[str, Any],
    step,
    trace_id: str,
    keywords: set[str],
    confirm: Callable[[str], bool],
    _ev: Callable[[str, dict[str, Any]], None],
    _tool_result_to_message: Callable[[str, ToolResult, set[str] | None], str],
) -> tuple[ToolResult, bool]:
    """
    处理步骤中的工具调用：统一生命周期 + 回喂。
    返回: (result, did_modify_code)
    """
    result = loop._run_tool_lifecycle(name, args, trace_id, confirm, _ev)
    did_modify_code = (name in {"write_file", "apply_patch", "undo_patch"} and result.ok)

    _ev("tool_result", {"tool": name, "ok": result.ok, "error": result.error, "payload": result.payload, "step_id": step.id})

    result_msg = _tool_result_to_message(name, result, keywords=keywords)
    loop.messages.append(ChatMessage(role="user", content=result_msg))
    loop.logger.debug(f"[dim]工具结果已回喂[/dim] [工具] {name} [步骤] {step.id}")
    loop.file_only_logger.debug(f"工具结果回喂 [step={step.id}] [tool={name}] [len={len(result_msg)}]")
    _ev("tool_result_fed_back", {"tool": name, "step_id": step.id})
    loop._trim_history(max_messages=30)

    return result, did_modify_code


def execute_single_step_iteration(
    loop: "AgentLoop",
    step,
    step_cursor: int,
    plan: Plan,
    iteration: int,
    trace_id: str,
    keywords: set[str],
    confirm: Callable[[str], bool],
    _ev: Callable[[str, dict[str, Any]], None],
    _llm_chat: Callable[[str, str | None], str],
    _try_parse_tool_call: Callable[[str], dict[str, Any] | None],
    _tool_result_to_message: Callable[[str, ToolResult, set[str] | None], str],
) -> tuple[str | None, bool, bool]:
    """
    执行单个计划步骤的一次 LLM 交互轮次。
    返回: (control_signal, did_modify_code, did_use_tool)
    """
    tools_hint = ", ".join(step.tools_expected) if step.tools_expected else "（未指定，模型自选）"
    loop.logger.info(
        f"[bold yellow]→ 执行步骤 {step_cursor + 1}/{len(plan.steps)}: {step.id}（轮次 {iteration + 1}/{loop.cfg.orchestrator.max_step_tool_calls}）[/bold yellow] "
        f"[描述] {step.description} [建议工具] {tools_hint}"
    )
    _ev("llm_request", {"messages": len(loop.messages), "step_id": step.id, "iteration": iteration + 1})

    loop._log_llm_request_params_to_file()

    step_prompt = (
        f"现在执行计划步骤：{step.id}\n"
        f"步骤描述：{step.description}\n"
        f"建议工具：{', '.join(step.tools_expected) if step.tools_expected else '（自行选择）'}\n\n"
        "规则：\n"
        "1) 如果需要工具：只输出一个工具调用 JSON（与系统要求一致）。\n"
        "2) 如果本步骤已完成且不需要工具：只输出字符串【STEP_DONE】。\n"
        "3) 如果本步骤失败且需要重规划：只输出字符串【REPLAN】。\n"
    )
    loop.messages.append(ChatMessage(role="user", content=step_prompt))
    loop._trim_history(max_messages=30)

    assistant = _llm_chat("execute_step", step.id)
    _ev("llm_response", {"text": assistant[:4000], "truncated": len(assistant) > 4000, "step_id": step.id})

    if assistant.count("[") > 50 or assistant.count("{") > 50:
        loop.logger.warning("[red]检测到模型输出异常（复读字符），已强制截断[/red]")
        assistant = "模型输出异常：检测到过多的重复字符，已强制截断。"
        _ev("stuttering_detected", {"length": len(assistant), "step_id": step.id})

    a_strip = assistant.strip()
    if "STEP_DONE" in a_strip or "【STEP_DONE】" in a_strip or a_strip.upper().startswith("STEP_DONE"):
        loop.messages.append(ChatMessage(role="assistant", content=assistant))
        loop._trim_history(max_messages=30)
        step.status = "done"
        loop.audit.write(trace_id=trace_id, event="plan_step_done", data={"step_id": step.id})
        _ev("plan_step_done", {"step_id": step.id})
        loop.logger.info(f"[green]✓ 步骤完成[/green] [步骤] {step.id} [描述] {step.description}")
        return "STEP_DONE", False, False

    if "REPLAN" in a_strip or "【REPLAN】" in a_strip or a_strip.upper().startswith("REPLAN"):
        loop.messages.append(ChatMessage(role="assistant", content=assistant))
        loop._trim_history(max_messages=30)
        step.status = "failed"
        loop.audit.write(trace_id=trace_id, event="plan_step_replan_requested", data={"step_id": step.id})
        _ev("plan_step_replan_requested", {"step_id": step.id})
        loop.logger.warning(f"[yellow]⚠ 步骤请求重规划[/yellow] [步骤] {step.id} [描述] {step.description}")
        return "REPLAN", False, False

    tool_call = _try_parse_tool_call(assistant)
    loop._log_llm_response_data_to_file(assistant, tool_call)
    if tool_call is None:
        loop.messages.append(ChatMessage(role="assistant", content=assistant))
        loop._trim_history(max_messages=30)
        loop.messages.append(ChatMessage(role="user", content="你的输出既不是工具调用 JSON，也不是【STEP_DONE】/【REPLAN】。请严格按规则输出。"))
        loop._trim_history(max_messages=30)
        return None, False, False

    name = tool_call["tool"]
    args = tool_call["args"]
    _ev("tool_call_parsed", {"tool": name, "args": args, "step_id": step.id})

    args_summary = loop._format_args_summary(name, args)
    loop.logger.info(f"[bold blue]🔧 解析到工具调用: {name}[/bold blue] [步骤] {step.id} [参数] {args_summary}")
    loop.file_only_logger.info(f"工具调用详情 [step_id={step.id}] [tool={name}] [args={json.dumps(args, ensure_ascii=False)}]")

    clean_assistant = json.dumps(tool_call, ensure_ascii=False)
    loop.messages.append(ChatMessage(role="assistant", content=clean_assistant))
    loop._trim_history(max_messages=30)

    result, did_modify_code = handle_tool_call_in_step(loop, name, args, step, trace_id, keywords, confirm, _ev, _tool_result_to_message)
    if result is None:
        return None, False, True
    return None, did_modify_code, True


def handle_replanning(
    loop: "AgentLoop",
    step,
    plan: Plan,
    replans_used: int,
    trace_id: str,
    tool_used: bool,
    _ev: Callable[[str, dict[str, Any]], None],
    _llm_chat: Callable[[str, str | None], str],
    _set_state: Callable[[AgentState, dict[str, Any] | None], None],
) -> tuple[Plan | None, int]:
    """处理重规划逻辑。返回: (new_plan, new_replans_used)"""
    if replans_used >= loop.cfg.orchestrator.max_replans:
        loop.logger.warning(f"[red]⚠ 达到最大重规划次数，停止[/red] [当前步骤] {step.id} [已用重规划] {replans_used}/{loop.cfg.orchestrator.max_replans}")
        _ev("stop_reason", {"reason": "max_replans_reached", "limit": loop.cfg.orchestrator.max_replans})
        return None, replans_used

    replans_used += 1
    _set_state(AgentState.RECOVERING, {"reason": "step_failed", "step_id": step.id, "replans_used": replans_used})
    _set_state(AgentState.PLANNING, {"reason": "replan", "replans_used": replans_used})

    replan_prompt = (
        "出现阻塞/失败，需要重规划。请输出新的 Plan JSON（严格 JSON，不要解释，不要调用工具）。\n"
        f"限制：steps 不超过 {loop.cfg.orchestrator.max_plan_steps}。\n"
        "请结合当前对话中的错误与工具反馈，生成更可执行的步骤。"
    )
    loop.messages.append(ChatMessage(role="user", content=replan_prompt))
    loop._trim_history(max_messages=30)
    assistant_plan = _llm_chat("replan", step.id)
    _ev("planning_llm_response", {"text": assistant_plan[:4000], "truncated": len(assistant_plan) > 4000})
    loop.messages.append(ChatMessage(role="assistant", content=assistant_plan))
    loop._trim_history(max_messages=30)

    try:
        from clude_code.orchestrator.planner import parse_plan_from_text, render_plan_markdown

        new_plan = parse_plan_from_text(assistant_plan)
        if len(new_plan.steps) > loop.cfg.orchestrator.max_plan_steps:
            new_plan.steps = new_plan.steps[: loop.cfg.orchestrator.max_plan_steps]
        loop.audit.write(trace_id=trace_id, event="replan_generated", data={"title": new_plan.title, "steps": [s.model_dump() for s in new_plan.steps]})
        _ev("replan_generated", {"title": new_plan.title, "steps": len(new_plan.steps), "replans_used": replans_used})
        loop.file_only_logger.info("重规划计划:\n" + render_plan_markdown(new_plan))
        return new_plan, replans_used
    except Exception as e:
        loop.logger.error(f"[red]✗ 重规划计划解析失败: {e}[/red]", exc_info=True)
        _ev("stop_reason", {"reason": "replan_parse_failed"})
        return None, replans_used


def execute_final_verification(
    loop: "AgentLoop",
    plan: Plan,
    did_modify_code: bool,
    trace_id: str,
    tool_used: bool,
    _ev: Callable[[str, dict[str, Any]], None],
    _set_state: Callable[[AgentState, dict[str, Any] | None], None],
) -> "AgentTurn | None":
    """最终验证阶段（仅在修改过代码时触发）。"""
    if not did_modify_code:
        return None

    _set_state(AgentState.VERIFYING, {"reason": "did_modify_code"})
    loop.logger.info("[bold magenta]🔍 最终验证阶段：运行自检[/bold magenta]")
    v_res = loop.verifier.run_verify()
    _ev("final_verify", {"ok": v_res.ok, "type": v_res.type, "summary": v_res.summary})

    if not v_res.ok:
        text = f"最终验证失败：{v_res.summary}\n"
        if v_res.errors:
            for err in v_res.errors[:10]:
                text += f"- {err.file}:{err.line} {err.message}\n"
        _set_state(AgentState.DONE, {"ok": False})
        from .models import AgentTurn

        return AgentTurn(assistant_text=text, tool_used=tool_used, trace_id=trace_id, events=[])
    return None


def execute_plan_steps(
    loop: "AgentLoop",
    plan: Plan,
    trace_id: str,
    keywords: set[str],
    confirm: Callable[[str], bool],
    events: list[dict[str, Any]],
    _ev: Callable[[str, dict[str, Any]], None],
    _llm_chat: Callable[[str, str | None], str],
    _try_parse_tool_call: Callable[[str], dict[str, Any] | None],
    _tool_result_to_message: Callable[[str, ToolResult, set[str] | None], str],
    _set_state: Callable[[AgentState, dict[str, Any] | None], None],
) -> tuple[Plan | None, bool, bool]:
    """
    执行计划的所有步骤（主循环）。
    返回: (plan, tool_used, did_modify_code)
    """
    _set_state(AgentState.EXECUTING, {"steps": len(plan.steps)})
    loop.logger.info("[bold magenta]▶ 进入执行阶段：按 Plan 步骤编排[/bold magenta]")

    replans_used = 0
    step_cursor = 0
    tool_used = False
    did_modify_code = False

    while True:
        if step_cursor >= len(plan.steps):
            break

        step = plan.steps[step_cursor]
        unmet_deps = check_step_dependencies(loop, step, plan, trace_id, _ev)
        if unmet_deps:
            step_cursor += 1
            continue

        step.status = "in_progress"
        loop.audit.write(trace_id=trace_id, event="plan_step_start", data={"step_id": step.id, "description": step.description})
        _ev("plan_step_start", {"step_id": step.id, "idx": step_cursor + 1, "total": len(plan.steps)})

        for iteration in range(loop.cfg.orchestrator.max_step_tool_calls):
            control_signal, iter_did_modify, iter_did_use_tool = execute_single_step_iteration(
                loop,
                step,
                step_cursor,
                plan,
                iteration,
                trace_id,
                keywords,
                confirm,
                _ev,
                _llm_chat,
                _try_parse_tool_call,
                _tool_result_to_message,
            )

            if iter_did_modify:
                did_modify_code = True
            if iter_did_use_tool:
                tool_used = True

            if control_signal in ("STEP_DONE", "REPLAN"):
                break

        if step.status == "done":
            step_cursor += 1
            continue

        if step.status in ("failed", "in_progress"):
            step.status = "failed"
            new_plan, replans_used = handle_replanning(loop, step, plan, replans_used, trace_id, tool_used, _ev, _llm_chat, _set_state)
            if new_plan is None:
                return None, tool_used, did_modify_code
            plan = new_plan
            step_cursor = 0
            continue

        if step.status == "blocked":
            all_blocked_or_done = all(s.status in ("blocked", "done") for s in plan.steps)
            if all_blocked_or_done and any(s.status == "blocked" for s in plan.steps):
                loop.logger.error("[red]✗ 检测到依赖死锁：所有未完成步骤都处于 blocked 状态[/red]")
                _ev("stop_reason", {"reason": "dependency_deadlock"})
                return None, tool_used, did_modify_code
            step_cursor += 1
            continue

        _ev("stop_reason", {"reason": "step_not_completed", "step_id": step.id})
        return None, tool_used, did_modify_code

    return plan, tool_used, did_modify_code


