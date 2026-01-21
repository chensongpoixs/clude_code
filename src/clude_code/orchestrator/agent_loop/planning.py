from __future__ import annotations

from typing import Any, Callable, TYPE_CHECKING

from clude_code.llm.llama_cpp_http import ChatMessage
from clude_code.orchestrator.planner import parse_plan_from_text, render_plan_markdown, Plan
from clude_code.orchestrator.state_m import AgentState
from clude_code.prompts import read_prompt

if TYPE_CHECKING:
    from .agent_loop import AgentLoop


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
        except Exception as e:
            loop.logger.error(f"[red]✗ 计划解析失败 (尝试 {plan_attempts}/{loop.cfg.orchestrator.planning_retry + 1}): {e}[/red]", exc_info=True)
            loop.audit.write(trace_id=trace_id, event="plan_parse_failed", data={"attempt": plan_attempts, "error": str(e)})
            _ev("plan_parse_failed", {"attempt": plan_attempts, "error": str(e)})
            loop.messages.append(ChatMessage(role="user", content=read_prompt("agent_loop/plan_parse_retry.md").strip()))
            loop._trim_history(max_messages=30)

    return None


