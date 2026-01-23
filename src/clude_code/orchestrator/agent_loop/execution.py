from __future__ import annotations

import json

from typing import Any, Callable, TYPE_CHECKING

from clude_code.llm.llama_cpp_http import ChatMessage
from clude_code.tooling.local_tools import ToolResult
from clude_code.orchestrator.state_m import AgentState
from clude_code.orchestrator.planner import Plan
from .control_protocol import try_parse_control_envelope
from clude_code.prompts import read_prompt, render_prompt




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
        _ev("plan_step_status_changed", {"step_id": step.id, "status": "blocked", "reason": f"unmet_deps: {unmet_deps}"})
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
    loop.logger.debug(f"[dim]工具结果已回喂[/dim] [工具] {name} [步骤] {step.id} [result_msg: {result_msg[:10]}{'...' if len(result_msg) > 10 else ''}]")
    loop.file_only_logger.debug(f"工具结果回喂 [step={step.id}] [tool={name}] [result_msg={result_msg}]")
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
    tools_hint = ", ".join(step.tools_expected) if step.tools_expected else "display（分析/总结类步骤）"
    loop.logger.info(
        f"[bold yellow]→ 执行步骤 {step_cursor + 1}/{len(plan.steps)}: {step.id}（轮次 {iteration + 1}/{loop.cfg.orchestrator.max_step_tool_calls}）[/bold yellow] "
        f"[描述] {step.description} [建议工具] {tools_hint}"
    )
    # 上报步骤开始事件
    if iteration == 0:
        _ev("plan_step_start", {"step_id": step.id, "idx": step_cursor + 1, "total": len(plan.steps)})
        _ev("plan_step_status_changed", {"step_id": step.id, "status": "in_progress"})

    _ev("llm_request", {"messages": len(loop.messages), "step_id": step.id, "iteration": iteration + 1})
    
    # 判断是否为分析/总结类步骤（无指定工具）
    is_analysis_step = not step.tools_expected or len(step.tools_expected) == 0
    # 兜底工具：分析类步骤默认使用 display
    tools_for_prompt = ", ".join(step.tools_expected) if step.tools_expected else "display（输出分析结果）"
    
    step_prompt = render_prompt(
        "user/stage/execute_step.j2",
        step_id=step.id,
        step_description=step.description,
        tools_expected=tools_for_prompt,
        is_analysis_step=is_analysis_step,
    ).strip()
    loop.messages.append(ChatMessage(role="user", content=step_prompt))
    loop._trim_history(max_messages=30)

    assistant = _llm_chat("execute_step", step.id)
    _ev("llm_response", {"text": assistant[:4000], "truncated": len(assistant) > 4000, "step_id": step.id})

    if assistant.count("[") > 50 or assistant.count("{") > 50:
        loop.logger.warning("[red]检测到模型输出异常（复读字符），已强制截断[/red]")
        assistant = "模型输出异常：检测到过多的重复字符，已强制截断。"
        _ev("stuttering_detected", {"length": len(assistant), "step_id": step.id})

    a_strip = assistant.strip()

    # P0-2：优先解析结构化控制协议（JSON Envelope / JSON 信封）
    ctrl = try_parse_control_envelope(a_strip)
    if ctrl is not None and ctrl.control == "step_done":
        loop.messages.append(ChatMessage(role="assistant", content=assistant))
        loop._trim_history(max_messages=30)
        step.status = "done"
        _ev("plan_step_status_changed", {"step_id": step.id, "status": "done"})
        loop.audit.write(trace_id=trace_id, event="plan_step_done", data={"step_id": step.id})
        _ev("plan_step_done", {"step_id": step.id})
        loop.logger.info(f"[green]✓ 步骤完成[/green] [步骤] {step.id} [描述] {step.description}")
        _ev("control_signal", {"control": "step_done", "step_id": step.id})
        return "STEP_DONE", False, False

    if ctrl is not None and ctrl.control == "replan":
        loop.messages.append(ChatMessage(role="assistant", content=assistant))
        loop._trim_history(max_messages=30)
        step.status = "failed"
        _ev("plan_step_status_changed", {"step_id": step.id, "status": "failed"})
        loop.audit.write(trace_id=trace_id, event="plan_step_replan_requested", data={"step_id": step.id})
        _ev("plan_step_replan_requested", {"step_id": step.id})
        loop.logger.warning(f"[yellow]⚠ 步骤请求重规划[/yellow] [步骤] {step.id} [描述] {step.description}")
        _ev("control_signal", {"control": "replan", "step_id": step.id})
        return "REPLAN", False, False

    # 兼容旧协议（但必须告警）：字符串 STEP_DONE/REPLAN
    if "STEP_DONE" in a_strip or "【STEP_DONE】" in a_strip or a_strip.upper().startswith("STEP_DONE"):
        loop.file_only_logger.warning(
            "检测到旧控制协议输出（STEP_DONE），已兼容处理。建议升级为 {\"control\":\"step_done\"}。",
            exc_info=False,
        )
        _ev("control_protocol_legacy", {"control": "step_done", "step_id": step.id})
        loop.messages.append(ChatMessage(role="assistant", content=assistant))
        loop._trim_history(max_messages=30)
        step.status = "done"
        loop.audit.write(trace_id=trace_id, event="plan_step_done", data={"step_id": step.id})
        _ev("plan_step_done", {"step_id": step.id})
        loop.logger.info(f"[green]✓ 步骤完成[/green] [步骤] {step.id} [描述] {step.description}")
        return "STEP_DONE", False, False

    if "REPLAN" in a_strip or "【REPLAN】" in a_strip or a_strip.upper().startswith("REPLAN"):
        loop.file_only_logger.warning(
            "检测到旧控制协议输出（REPLAN），已兼容处理。建议升级为 {\"control\":\"replan\"}。",
            exc_info=False,
        )
        _ev("control_protocol_legacy", {"control": "replan", "step_id": step.id})
        loop.messages.append(ChatMessage(role="assistant", content=assistant))
        loop._trim_history(max_messages=30)
        step.status = "failed"
        loop.audit.write(trace_id=trace_id, event="plan_step_replan_requested", data={"step_id": step.id})
        _ev("plan_step_replan_requested", {"step_id": step.id})
        loop.logger.warning(f"[yellow]⚠ 步骤请求重规划[/yellow] [步骤] {step.id} [描述] {step.description}")
        return "REPLAN", False, False

    tool_call = _try_parse_tool_call(assistant)
    if tool_call is None:
        loop.messages.append(ChatMessage(role="assistant", content=assistant))
        loop._trim_history(max_messages=30)
        
        # P2 修复：错误消息去重，避免重试循环导致消息雪崩
        error_prompt = read_prompt("user/stage/invalid_step_output_retry.md").strip()
        last_user_msg = next((m for m in reversed(loop.messages) if m.role == "user"), None)
        if last_user_msg and "你的输出既不是工具调用" in last_user_msg.content:
            # 已有错误提示，不再追加（避免雪崩）
            loop.logger.debug("[dim]跳过重复错误提示（已存在）[/dim]")
        else:
            loop.messages.append(ChatMessage(role="user", content=error_prompt))
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

    # P0-3：优先局部重规划（PlanPatch），失败回退全量 Plan（兼容迁移期）
    try:
        from clude_code.orchestrator.planner import render_plan_markdown
        cur_plan_md = render_plan_markdown(plan)
    except Exception as e:
        # P1-1: 渲染失败不阻塞主流程，但记录日志便于排查
        loop.file_only_logger.warning(f"render_plan_markdown 失败: {e}", exc_info=True)
        cur_plan_md = "(render_plan_markdown 失败，略)"
    #  从新规划提示生成重规划提示
    replan_prompt = render_prompt(
        "user/stage/replan.j2",
        max_plan_steps=int(loop.cfg.orchestrator.max_plan_steps),
        step_id=step.id,
        step_description=step.description,
        step_status=step.status,
        step_dependencies=step.dependencies,
        cur_plan_md=cur_plan_md,
    ).strip()

    # 允许一次“补丁纠错重试”：常见失败原因是补丁内部冲突（例如同一步骤既 remove 又 update）
    from clude_code.orchestrator.planner import (
        apply_plan_patch,
        carry_over_done_status,
        parse_plan_from_text,
        parse_plan_patch_from_text,
        render_plan_markdown,
    )

    def _apply_patch_or_raise(assistant_text: str) -> Plan:
        # P0: 预检 type 字段——如果 LLM 明确输出 FullPlan，直接跳过 PlanPatch 解析
        import json as _json
        import re as _re
        _json_match = _re.search(r'\{[\s\S]*\}', assistant_text)
        if _json_match:
            try:
                _obj = _json.loads(_json_match.group())
                if isinstance(_obj, dict) and _obj.get("type") == "FullPlan":
                    raise ValueError("LLM 输出 type='FullPlan'，应走 full Plan 解析路径")
            except _json.JSONDecodeError:
                pass  # 交给后续 parse_plan_patch_from_text 处理
        
        patch = parse_plan_patch_from_text(assistant_text)
        new_plan, meta = apply_plan_patch(plan, patch, max_plan_steps=int(loop.cfg.orchestrator.max_plan_steps))
        # 防止误判：如果补丁是"空操作"，视为无效
        title_changed = bool((patch.title or "").strip())
        if (meta.get("added", 0) + meta.get("updated", 0) + meta.get("removed", 0)) == 0 and not title_changed:
            raise ValueError("PlanPatch 是空操作（无新增/更新/删除/标题更新），拒绝应用")
        loop.audit.write(
            trace_id=trace_id,
            event="plan_patch_applied",
            data={"step_id": step.id, "meta": meta, "reason": patch.reason, "replans_used": replans_used},
        )
        _ev(
            "plan_patch_applied",
            {
                "type": "PlanPatch",  # 标识重规划类型
                "step_id": step.id,
                "meta": meta,
                "reason": patch.reason,
                "replans_used": replans_used,
                "steps": [s.model_dump() for s in new_plan.steps],
                "title": new_plan.title,
                "verification_policy": new_plan.verification_policy,
            },
        )
        loop.file_only_logger.info("计划补丁已应用:\n" + render_plan_markdown(new_plan))
        return new_plan

    last_assistant_plan: str | None = None
    last_patch_error: Exception | None = None
    retry_prompt: str | None = None

    for attempt in range(2):  # 第 0 次正常；第 1 次补丁纠错重试
        prompt = replan_prompt if attempt == 0 else (retry_prompt or replan_prompt)
        loop.messages.append(ChatMessage(role="user", content=prompt))
        loop._trim_history(max_messages=30)
        assistant_plan = _llm_chat("replan", step.id)
        last_assistant_plan = assistant_plan
        _ev("planning_llm_response", {"text": assistant_plan[:4000], "truncated": len(assistant_plan) > 4000, "attempt": attempt + 1})
        loop.messages.append(ChatMessage(role="assistant", content=assistant_plan))
        loop._trim_history(max_messages=30)

        try:
            # 1) 优先尝试 PlanPatch
            new_plan = _apply_patch_or_raise(assistant_plan)
            return new_plan, replans_used
        except Exception as e:
            last_patch_error = e
            # 第一次失败则准备 retry prompt（从 prompts/ 目录加载）
            retry_prompt = render_prompt(
                "user/stage/plan_patch_retry.j2",
                error_type=type(e).__name__,
                error_message=str(e),
            )
            if attempt == 0:
                continue

    # 2) 两次 PlanPatch 都失败：才回退 full Plan（旧协议）
    try:
        assistant_text = last_assistant_plan or ""
        new_plan = parse_plan_from_text(assistant_text)
        new_plan = carry_over_done_status(plan, new_plan)
        if len(new_plan.steps) > loop.cfg.orchestrator.max_plan_steps:
            new_plan.steps = new_plan.steps[: loop.cfg.orchestrator.max_plan_steps]
        loop.audit.write(trace_id=trace_id, event="replan_generated", data={"type": "FullPlan", "title": new_plan.title, "steps": [s.model_dump() for s in new_plan.steps]})
        _ev("replan_generated", {"type": "FullPlan", "title": new_plan.title, "steps": len(new_plan.steps), "replans_used": replans_used})
        loop.file_only_logger.info("重规划计划:\n" + render_plan_markdown(new_plan))
        return new_plan, replans_used
    except Exception as e2:
        # 若模型给的是 PlanPatch（缺少 steps），这里的报错会非常误导；统一报更明确的错误
        loop.logger.error(
            f"[red]✗ 重规划解析失败[/red] patch_error={last_patch_error} full_plan_error={e2}",
            exc_info=True,
        )
        _ev("stop_reason", {"reason": "replan_parse_failed", "patch_error": str(last_patch_error or ""), "full_plan_error": str(e2)})
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
    loop.logger.info("[bold magenta]🔍 最终验证阶段：运行自检 (选择性测试)[/bold magenta]")
    v_res = loop.verifier.run_verify(modified_paths=list(loop._turn_modified_paths))
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
        # P0-3：局部重规划会保留 done 步骤，必须跳过，避免重复执行/状态被覆盖
        if getattr(step, "status", None) == "done":
            step_cursor += 1
            continue
        unmet_deps = check_step_dependencies(loop, step, plan, trace_id, _ev)
        if unmet_deps:
            step_cursor += 1
            continue

        step.status = "in_progress"
        loop.audit.write(trace_id=trace_id, event="plan_step_start", data={"step_id": step.id, "description": step.description})
        _ev("plan_step_start", {"step_id": step.id, "idx": step_cursor + 1, "total": len(plan.steps)})
        # 执行步骤的多轮迭代
        for iteration in range(loop.cfg.orchestrator.max_step_tool_calls):
            # 执行单步迭代
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
        # 处理步骤状态
        if step.status == "done":
            step_cursor += 1
            continue

        if step.status in ("failed", "in_progress"):
            step.status = "failed"
            # 处理重规划
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


