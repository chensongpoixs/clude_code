from __future__ import annotations

import json
from typing import Any, Callable, TYPE_CHECKING

from clude_code.llm.http_client import ChatMessage
from clude_code.orchestrator.planner import parse_plan_from_text, render_plan_markdown, Plan, PlanStep
from clude_code.orchestrator.state_m import AgentState
from clude_code.prompts import read_prompt

if TYPE_CHECKING:
    from .agent_loop import AgentLoop


def _try_convert_tool_call_to_plan(text: str, loop: "AgentLoop") -> Plan | None:
    """
    尝试将工具调用 JSON 转换为 Plan。
    
    当 LLM 误输出工具调用格式时，自动转换为单步 Plan。
    
    检测模式:
    - {"tool": "xxx", "args": {...}}
    - {"tool": "xxx", "params": {...}}
    
    Args:
        text: LLM 输出的文本
        loop: AgentLoop 实例
    
    Returns:
        Plan 对象或 None（无法转换）
    """
    try:
        # 尝试解析 JSON
        data = json.loads(text.strip())
        
        # 必须是字典
        if not isinstance(data, dict):
            return None
        
        # 必须有 tool 字段
        tool_name = data.get("tool")
        if not tool_name or not isinstance(tool_name, str):
            return None
        
        # 必须有 args 或 params 字段（工具调用特征）
        if "args" not in data and "params" not in data:
            return None
        
        # 不能有 type 字段（避免误判 Plan）
        if "type" in data:
            return None
        
        # 构建单步 Plan
        step = PlanStep(
            id="step_1",
            description=f"使用 {tool_name} 工具执行任务",
            dependencies=[],
            tools_expected=[tool_name],
            status="pending"
        )
        
        plan = Plan(
            type="FullPlan",
            title=f"执行 {tool_name}",
            steps=[step]
        )
        
        loop.logger.info(
            f"[yellow]⚠ 检测到工具调用输出，已自动转换为 Plan[/yellow]: "
            f"tool={tool_name}"
        )
        
        return plan
    except (json.JSONDecodeError, ValueError, KeyError, AttributeError):
        # 无法解析或转换，返回 None
        return None


def execute_planning_phase(
    loop: "AgentLoop",
    user_text: str,
    planning_prompt: str | None,
    trace_id: str,
    _ev: Callable[[str, dict[str, Any]], None],
    _llm_chat: Callable[[str, str | None], str],
) -> Plan | None:
    """执行规划阶段：生成显式 Plan。"""
    if not planning_prompt:
        return None

    _ev("state", {"state": AgentState.PLANNING.value, "reason": "enable_planning"})
    loop.logger.info("[bold magenta]🧩 进入规划阶段：生成显式 Plan[/bold magenta]")

    plan_attempts = 0
    while plan_attempts <= loop.cfg.orchestrator.planning_retry:
        plan_attempts += 1
        _ev("planning_llm_request", {"attempt": plan_attempts})

        # 记录调用_llm_chat之前的消息长度，用于后续清理
        messages_before_llm = len(loop.messages)

        assistant_plan = _llm_chat("planning", None)
        _ev("planning_llm_response", {"text": assistant_plan[:4000], "truncated": len(assistant_plan) > 4000})

        try:
            parsed = parse_plan_from_text(assistant_plan)
            if len(parsed.steps) > loop.cfg.orchestrator.max_plan_steps:
                parsed.steps = parsed.steps[: loop.cfg.orchestrator.max_plan_steps]
            plan = parsed

            # 强制校验步骤 ID 唯一性（parse_plan_from_text 已校验，这里做双保险）
            plan.validate_unique_ids()

            # 只有在成功时才添加assistant消息到历史
            loop.messages.append(ChatMessage(role="assistant", content=assistant_plan))
            loop._trim_history(max_messages=30)

            loop.audit.write(trace_id=trace_id, event="plan_generated", data={"title": plan.title, "steps": [s.model_dump() for s in plan.steps]})
            # 为 live UI / TUI 提供可读的计划预览（避免只给一个 steps 数字）
            steps_preview: list[str] = []
            for s in plan.steps[: min(8, len(plan.steps))]:
                sid = str(getattr(s, "id", "") or "").strip()
                desc = str(getattr(s, "description", "") or "").strip()
                line = f"{sid}: {desc}" if sid else desc
                if len(line) > 140:
                    line = line[:139] + "…"
                if line:
                    steps_preview.append(line)
            _ev(
                "plan_generated",
                {
                    "type": "FullPlan",  # 初始规划类型
                    "title": plan.title,
                    "steps_count": len(plan.steps),
                    "steps": [s.model_dump() for s in plan.steps],
                    "verification_policy": plan.verification_policy,
                },
            )
            loop.logger.info("[green]✓ 计划生成成功[/green]")
            plan_summary = render_plan_markdown(plan)
            loop.logger.info(f"[dim]计划摘要:\n{plan_summary}[/dim]")
            return plan
        except ValueError as e:
            # 尝试容错：检测是否为工具调用输出
            tool_call_plan = _try_convert_tool_call_to_plan(assistant_plan, loop)
            if tool_call_plan:
                # 成功转换，使用转换后的 Plan
                plan = tool_call_plan
                
                # 添加到历史
                loop.messages.append(ChatMessage(role="assistant", content=assistant_plan))
                loop._trim_history(max_messages=30)
                
                loop.audit.write(
                    trace_id=trace_id,
                    event="plan_generated_from_tool_call",
                    data={
                        "title": plan.title,
                        "steps": [s.model_dump() for s in plan.steps],
                        "warning": "LLM 输出工具调用而非 Plan，已自动转换"
                    }
                )
                
                _ev(
                    "plan_generated",
                    {
                        "type": "FullPlan",
                        "title": plan.title,
                        "steps_count": len(plan.steps),
                        "steps": [s.model_dump() for s in plan.steps],
                        "from_tool_call": True,
                    },
                )
                
                loop.logger.info("[green]✓ 计划生成成功（从工具调用转换）[/green]")
                plan_summary = render_plan_markdown(plan)
                loop.logger.info(f"[dim]计划摘要:\n{plan_summary}[/dim]")
                return plan
            
            # 无法容错，记录错误并重试
            loop.logger.error(f"[red]✗ 计划解析失败 (尝试 {plan_attempts}/{loop.cfg.orchestrator.planning_retry + 1}): {e}[/red]", exc_info=True)
            loop.audit.write(trace_id=trace_id, event="plan_parse_failed", data={"attempt": plan_attempts, "error": str(e)})
            _ev("plan_parse_failed", {"attempt": plan_attempts, "error": str(e)})
            loop.messages.append(ChatMessage(role="user", content=read_prompt("user/stage/plan_parse_retry.md").strip()))
            loop._trim_history(max_messages=30)
        except Exception as e:
            # 其他异常，直接记录并重试
            loop.logger.error(f"[red]✗ 计划解析失败 (尝试 {plan_attempts}/{loop.cfg.orchestrator.planning_retry + 1}): {e}[/red]", exc_info=True)
            loop.audit.write(trace_id=trace_id, event="plan_parse_failed", data={"attempt": plan_attempts, "error": str(e)})
            _ev("plan_parse_failed", {"attempt": plan_attempts, "error": str(e)})
            loop.messages.append(ChatMessage(role="user", content=read_prompt("user/stage/plan_parse_retry.md").strip()))
            loop._trim_history(max_messages=30)

    return None


