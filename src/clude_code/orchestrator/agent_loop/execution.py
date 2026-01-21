from __future__ import annotations

import json

from jinja2 import Template;

from typing import Any, Callable, TYPE_CHECKING

from clude_code.llm.llama_cpp_http import ChatMessage
from clude_code.tooling.local_tools import ToolResult
from clude_code.orchestrator.state_m import AgentState
from clude_code.orchestrator.planner import Plan
from .control_protocol import try_parse_control_envelope




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
    tools_hint = ", ".join(step.tools_expected) if step.tools_expected else "（未指定，模型自选）"
    loop.logger.info(
        f"[bold yellow]→ 执行步骤 {step_cursor + 1}/{len(plan.steps)}: {step.id}（轮次 {iteration + 1}/{loop.cfg.orchestrator.max_step_tool_calls}）[/bold yellow] "
        f"[描述] {step.description} [建议工具] {tools_hint}"
    )
    _ev("llm_request", {"messages": len(loop.messages), "step_id": step.id, "iteration": iteration + 1})
    # @date:2026-01-20 改进步骤执行提示词，
    # 原因是大模型返回时常出现理解偏差，导致输出不符合预期（如输出多余文字、未按要求输出 JSON 等）
    # ===== 本轮 LLM 返回文本 =====
    #--- assistant_text ---
    #```json
    #{
    #"control": "step_done"
    #}
    #```
    #########################################
    # step_prompt = (
    #     f"现在执行计划步骤：{step.id}\n"
    #     f"步骤描述：{step.description}\n"
    #     f"建议工具：{', '.join(step.tools_expected) if step.tools_expected else '（自行选择）'}\n\n"
    #     "规则：\n"
    #     "0) 业界标准：步骤开始/关键进展时，优先调用 display 输出一条简短进度（level=progress/info）。\n"
    #     "1) 如果需要工具：只输出一个工具调用 JSON（与系统要求一致）。\n"
    #     "2) 如果本步骤已完成且不需要工具：只输出控制 JSON：{\"control\":\"step_done\"}。\n"
    #     "3) 如果本步骤失败且需要重规划：只输出控制 JSON：{\"control\":\"replan\"}。\n"
    # )
    # 解决上面LLM输出不符合预期的问题后，保留原有提示词结构，但加强了规则的明确性和细节描述
    step_prompt = (
    f"【当前执行步骤】：{step.id}\n"
    f"【核心任务目标】：{step.description}\n"
    f"【可用工具集】：{', '.join(step.tools_expected) if step.tools_expected else '根据需求自主选择'}\n\n"
    "## 强制执行规则：\n"
    "1. 动作唯一性：单次回复仅允许执行一个动作（调用一个工具 或 输出一个控制JSON）。\n"
    "2. 工具调用：若需操作，直接输出工具调用。建议在调用核心工具前，若有重大进展，可先通过 display 工具汇报 level='progress' 的简报。\n"
    "3. 状态闭环：\n"
    "   - 成功判定：若步骤目标已达成，输出且仅输出：{\"control\": \"step_done\"}\n"
    "   - 无法继续：若环境报错或逻辑无法自洽，输出且仅输出：{\"control\": \"replan\", \"reason\": \"原因描述\"}\n"
    "4. 严禁废话：不要输出任何开场白、解释或总结文字，只输出工具 JSON 或控制 JSON。"
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

    # P0-2：优先解析结构化控制协议（JSON Envelope / JSON 信封）
    ctrl = try_parse_control_envelope(a_strip)
    if ctrl is not None and ctrl.control == "step_done":
        loop.messages.append(ChatMessage(role="assistant", content=assistant))
        loop._trim_history(max_messages=30)
        step.status = "done"
        loop.audit.write(trace_id=trace_id, event="plan_step_done", data={"step_id": step.id})
        _ev("plan_step_done", {"step_id": step.id})
        loop.logger.info(f"[green]✓ 步骤完成[/green] [步骤] {step.id} [描述] {step.description}")
        _ev("control_signal", {"control": "step_done", "step_id": step.id})
        return "STEP_DONE", False, False

    if ctrl is not None and ctrl.control == "replan":
        loop.messages.append(ChatMessage(role="assistant", content=assistant))
        loop._trim_history(max_messages=30)
        step.status = "failed"
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
        loop.messages.append(
            ChatMessage(
                role="user",
                content="你的输出既不是工具调用 JSON，也不是控制 JSON（{\"control\":\"step_done\"}/{\"control\":\"replan\"}）。请严格按规则输出。",
            )
        )
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
    concurrency = 0;#  loop.cfg.executor.concurrency;
    # replan_prompt = (
    #     "出现阻塞/失败，需要重规划。\n"
    #     "优先输出 PlanPatch JSON（严格 JSON，不要解释，不要调用工具）：\n"
    #     "{\n"
    #     '  "title": "可选：新标题",\n'
    #     '  "remove_steps": ["step_x"],\n'
    #     '  "update_steps": [{"id":"step_3","description":"...","dependencies":["step_1"],"tools_expected":["grep"]}],\n'
    #     '  "add_steps": [{"id":"step_4","description":"...","dependencies":["step_3"],"tools_expected":["read_file"],"status":"pending"}],\n'
    #     '  "reason": "可选：为什么这样 patch"\n'
    #     "}\n"
    #     "约束：\n"
    #     f"- steps 总数不超过 {loop.cfg.orchestrator.max_plan_steps}\n"
    #     "- 禁止删除/修改 status=done 的步骤\n"
    #     "- 新增步骤的 status 会被强制设为 pending\n"
    #     "\n"
    #     "当前失败步骤：\n"
    #     f"- step_id={step.id}\n"
    #     f"- description={step.description}\n"
    #     "\n"
    #     "当前 Plan（含状态/依赖/建议工具）：\n"
    #     f"{cur_plan_md}\n"
    #     "\n"
    #     "如果你确实无法用 PlanPatch 表达（极少数情况），才允许输出完整 Plan JSON（严格 JSON）。"
    # )
   
    replan_prompt = (
        "# Role \n"
        "你是任务规划器的重规划模块（Replanner）。\n"
        "你唯一职责是根据失败步骤生成 PlanPatch，修补当前计划。\n"
        "禁止执行任何操作，只输出严格 JSON。\n"
        "\n"
        "# Rules\n"
        "1. 输出 JSON 严格格式，不允许任何解释性文字。\n"
        "2. 优先使用 PlanPatch 修复计划：\n"
        "   - remove_steps：移除步骤\n"
        "   - update_steps：更新步骤信息\n"
        "   - add_steps：新增步骤\n"
        "3. 仅在 PlanPatch 无法表达修复时，才输出完整 Plan JSON。\n"
        "4. 禁止删除或修改 status=\"done\" 的步骤。\n"
        "5. add_steps 的 status 必须为 \"pending\"。\n"
        "6. remove_steps、update_steps、add_steps 的 id 必须唯一，不与已有步骤冲突。\n"
        "7. 删除步骤前必须检查是否被其他步骤依赖，不能破坏依赖链。\n"
        "\n"
        "# JSON Output Format (PlanPatch)\n"
        "{\n"
        "\"title\": \"可选：新标题，必填时替换旧标题\",\n"
        f"\"remove_steps\": [\"step_x\"],\n"
        "\"update_steps\": [\n"
            "{\n"
            "            \"id\": \"step_3\",\n"
            "            \"description\": \"必填：完整描述更新后的动作\",\n"
            "            \"dependencies\": [\"step_id1\",\"step_id2\"],\n"
            "            \"tools_expected\": [\"tool_name\"],\n"
            "            \"status\": \"pending 或原状态，如果非 done\"\n"
            "}\n"
        "],\n"
        "\"add_steps\": [\n"
            "{\n"
            "            \"id\": \"step_4\",\n"
            "            \"description\": \"必填：完整描述新增动作\",\n"
            "            \"dependencies\": [\"step_3\"],\n"
            "            \"tools_expected\": [\"tool_name\"],\n"
            "            \"status\": \"pending\"\n"
            "}\n"
        "],\n"
        "\"reason\": \"可选：说明为何进行此修补\"\n"
        "}\n"

        "# Input Context (Jinja Template)\n"
        "- 当前失败步骤：\n"
        f"- step_id={step.id}\n"
        f"- description={step.description}\n"
        "- 当前 Plan（含状态/依赖/建议工具）：\n"
        f"{cur_plan_md}\n" 
        "# Execution Settings\n"
        f"- 并发控制：-c {concurrency}   # 填 0 自动按系统合理并发执行\n"
        f"- 模板渲染：启用 Jinja，占位符 {step.id}, {loop.index}, {cur_plan_md}, {concurrency} 可自动替换\n"
        "- 输出要求：仅 JSON，不允许自然语言\n"

        "# Instructions for Loop Execution\n"
        "{% for step in failed_steps %}\n"
        "- 生成 PlanPatch 针对 step    {{step.id}}\n"
        "- 使用并发控制 {{concurrency}}\n"
        "{% endfor %} ");

     # bingfeng: 2024-10-15 优化提示词，增强可控性和输出质量
    # ----------------------------
    # 模拟输入数据
    # ----------------------------

    # failed_steps = [
    #     {"id": "step_2", "description": "检查配置文件是否存在"},
    #     {"id": "step_5", "description": "读取数据并解析"}
    # ]

    # # 当前计划的简化 JSON（可以根据实际 Plan 替换）
    # # cur_plan_md = """{
    # # "title": "原始任务计划",
    # # "steps": [
    # #     {"id": "step_1", "description": "初始化环境", "status": "done", "dependencies": [], "tools_expected": ["init_tool"]},
    # #     {"id": "step_2", "description": "检查配置文件是否存在", "status": "failed", "dependencies": ["step_1"], "tools_expected": ["read_file"]},
    # #     {"id": "step_5", "description": "读取数据并解析", "status": "failed", "dependencies": ["step_3"], "tools_expected": ["parse_tool"]}
    # # ]
    # # }"""
    # concurrency = 0;#  loop.cfg.executor.concurrency;
    # # ----------------------------
    # # Jinja 模板
    # # ----------------------------

    # replan_template = """
    # # Role
    # 你是任务规划器的重规划模块（Replanner）。
    # 你唯一职责是根据失败步骤生成 PlanPatch，修补当前计划。
    # 禁止执行任何操作，只输出严格 JSON。

    # # JSON Output Format (PlanPatch)
    # {
    # "title": "可选：新标题，必填时替换旧标题",
    # "remove_steps": [],
    # "update_steps": [
    # {% for step in failed_steps %}
    #     {
    #         "id": "{{ step.id }}",
    #         "description": "{{ step.description }} - 修补后描述",
    #         "dependencies": ["step_1"],
    #         "tools_expected": ["read_file"],
    #         "status": "pending"
    #     }{% if not loop.last %},{% endif %}
    # {% endfor %}
    # ],
    # "add_steps": [
    # {% for step in failed_steps %}
    #     {
    #         "id": "{{ step.id }}_new",
    #         "description": "新增操作步骤，依赖 {{ step.id }}",
    #         "dependencies": ["{{ step.id }}"],
    #         "tools_expected": ["read_file"],
    #         "status": "pending"
    #     }{% if not loop.last %},{% endif %}
    # {% endfor %}
    # ],
    # "reason": "自动生成 PlanPatch 修复失败步骤"
    # }

    # # 当前 Plan（含状态/依赖/建议工具）：
    # {{ cur_plan_md }}

    # # 并发控制：
    # -c {{ concurrency }}

    # # Instructions for Loop Execution
    # {% for step in failed_steps %}
    # - 生成 PlanPatch 针对 step {{ step.id }}
    # - 使用并发控制 {{ concurrency }}
    # {% endfor %}
    # """
    # template = Template(replan_template)
    # replan_prompt = template.render(
    #     failed_steps=failed_steps,
    #     cur_plan_md=cur_plan_md,
    #     concurrency=concurrency
    # )



    loop.messages.append(ChatMessage(role="user", content=replan_prompt))
    loop._trim_history(max_messages=30)
    assistant_plan = _llm_chat("replan", step.id)
    _ev("planning_llm_response", {"text": assistant_plan[:4000], "truncated": len(assistant_plan) > 4000})
    loop.messages.append(ChatMessage(role="assistant", content=assistant_plan))
    loop._trim_history(max_messages=30)

    try:
        from clude_code.orchestrator.planner import (
            apply_plan_patch,
            carry_over_done_status,
            parse_plan_from_text,
            parse_plan_patch_from_text,
            render_plan_markdown,
        )

        # 1) 优先解析/应用 PlanPatch（P0-3）
        try:
            patch = parse_plan_patch_from_text(assistant_plan)
            new_plan, meta = apply_plan_patch(
                plan,
                patch,
                max_plan_steps=int(loop.cfg.orchestrator.max_plan_steps),
            )
            # 防止误判：如果补丁是“空操作”，视为无效，回退 full Plan
            title_changed = bool((patch.title or "").strip())
            if (meta.get("added", 0) + meta.get("updated", 0) + meta.get("removed", 0)) == 0 and not title_changed:
                raise ValueError("PlanPatch 是空操作（无新增/更新/删除/标题更新），拒绝应用并回退 full Plan")
            loop.audit.write(
                trace_id=trace_id,
                event="plan_patch_applied",
                data={"step_id": step.id, "meta": meta, "reason": patch.reason, "replans_used": replans_used},
            )
            _ev(
                "plan_patch_applied",
                {"step_id": step.id, "meta": meta, "reason": patch.reason, "replans_used": replans_used, "steps": len(new_plan.steps)},
            )
            loop.file_only_logger.info("计划补丁已应用:\n" + render_plan_markdown(new_plan))
            return new_plan, replans_used
        except Exception as e:
            # patch 失败：回退全量 Plan（兼容迁移期）
            loop.file_only_logger.warning(f"PlanPatch 解析/应用失败，回退 full Plan: {e}", exc_info=True)

        # 2) 回退：解析 full Plan（旧协议）
        new_plan = parse_plan_from_text(assistant_plan)
        new_plan = carry_over_done_status(plan, new_plan)
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


