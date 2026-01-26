"""
Agent Loop 规划模块 (修复版)
处理复杂任务的规划和执行协调
"""
import uuid
import json
from typing import Any, Dict, Optional, List, Union
from dataclasses import dataclass

from clude_code.llm.http_client import ChatMessage
from clude_code.observability.logger import get_logger
from clude_code.orchestrator.planner import Plan, Step, parse_plan_from_text

# ============================================================================
# 核心规划函数 (修复版)
# ============================================================================

def detect_model_response_type(text: str) -> str:
    """检测模型响应的类型，用于更好的错误处理"""
    text = text.strip()
    
    if not text or len(text) < 10:
        return 'empty'
    
    # 检查是否包含JSON结构
    has_json_start = '{' in text and '}' in text
    has_fenced = '```' in text
    
    # 检查是否为对话式文本（中文响应）
    conversational_indicators = [
        '好的', '明白', '我理解', '知道了', '请您', '请描述', 
        '我会按照', '我来', '让我', '我将', '明白了', '理解了',
        '好的，明白了', '我明白了', '我知道了'
    ]
    
    is_conversational = any(indicator in text for indicator in conversational_indicators)
    
    if not has_json_start and not has_fenced and is_conversational:
        return 'conversational'
    elif (has_json_start or has_fenced) and is_conversational:
        return 'mixed'
    elif has_json_start or has_fenced:
        return 'json'
    else:
        return 'unknown'

def _extract_json_candidates(text: Optional[Union[str, bytes]]) -> List[str]:
    """改进的JSON候选提取，处理更多边界情况"""
    t = (text or "").strip()
    cands: List[str] = []
    
    # 1. 优先处理 fenced code blocks
    if "```" in t:
        # 更精确的fenced JSON提取
        import re
        patterns = [
            r'```(?:json|JSON)\\s*\\n(.*?)\\n```',
            r'```\\s*\\n(.*?)\\n```',
            r'```(?:json|JSON)\\s*(.*?)\\s*```',
            r'```\\s*(.*?)\\s*```'
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, t, re.DOTALL | re.IGNORECASE)
            for match in matches:
                candidate = match.strip()
                if candidate.startswith("{") and candidate.endswith("}"):
                    cands.append(candidate)
    
    # 2. 纯JSON检测（更严格）
    if t.startswith("{") and t.endswith("}"):
        cands.append(t)
    
    # 3. 智能括号匹配（处理嵌套）
    if "{" in t and "}" in t:
        stack = []
        start_idx = None
        
        for i, char in enumerate(t):
            if char == '{':
                if not stack:
                    start_idx = i
                stack.append('{')
            elif char == '}':
                if stack:
                    stack.pop()
                    if not stack and start_idx is not None:
                        candidate = t[start_idx:i+1].strip()
                        if candidate.startswith("{") and candidate.endswith("}"):
                            if candidate not in cands:
                                cands.append(candidate)
    
    return cands

def parse_plan_from_text(text: str) -> Plan:
    """解析 Plan JSON，改进版本"""
    # 尝试多种解析策略
    candidates = _extract_json_candidates(text)
    
    if not candidates:
        # 检测为什么没有找到JSON
        response_type = detect_model_response_type(text)
        if response_type == 'conversational':
            raise ValueError(
                "模型输出是对话式文字而非JSON。\\n"
                "请确保模型只输出JSON对象，不要包含解释文字。\\n"
                f"原始输出: {text[:200]}..."
            )
        else:
            raise ValueError(
                "无法从模型输出中找到有效的JSON格式。\\n"
                "请确保输出包含有效的JSON对象或使用 ```json ``` 代码块。\\n"
                f"原始输出: {text[:200]}..."
            )
    
    # 尝试解析每个候选
    errors = []
    for i, candidate in enumerate(candidates):
        try:
            plan_data = json.loads(candidate)
            
            # 创建Plan对象
            plan = Plan(
                title=plan_data.get("title", ""),
                steps=[],
                assumptions=plan_data.get("assumptions", []),
                constraints=plan_data.get("constraints", []),
                risks=plan_data.get("risks", []),
                verification_policy=plan_data.get("verification_policy", "run_verify")
            )
            
            # 解析步骤
            for step_data in plan_data.get("steps", []):
                step = Step(
                    id=step_data.get("id", f"step_{len(plan.steps) + 1}"),
                    description=step_data.get("description", ""),
                    expected_output=step_data.get("expected_output", ""),
                    dependencies=step_data.get("dependencies", []),
                    tools_expected=step_data.get("tools_expected", [])
                )
                plan.steps.append(step)
            
            return plan
            
        except (json.JSONDecodeError, KeyError, ValueError, TypeError) as e:
            errors.append(f"Candidate {i+1}: {str(e)}")
            continue
    
    # 如果所有候选都解析失败
    error_detail = "\\n".join(errors)
    raise ValueError(
        f"无法解析任何JSON候选。\\n"
        f"错误详情: {error_detail}\\n"
        f"原始输出: {text[:500]}..."
    )

def _try_convert_tool_call_to_plan(assistant_plan: str, loop) -> Plan | None:
    """尝试将工具调用转换为 Plan"""
    try:
        # 简化的工具调用检测
        if '"tool":' in assistant_plan and '"args":' in assistant_plan:
            # 假设这是工具调用，尝试创建简单计划
            return Plan(
                title="从工具调用自动转换的计划",
                steps=[
                    Step(
                        id="step_1", 
                        description="执行用户请求的操作",
                        expected_output="操作执行结果",
                        dependencies=[],
                        tools_expected=["unknown"]  # 需要从工具调用中提取
                    )
                ],
                assumptions=["用户请求可转换为步骤"],
                constraints=["需要手动验证步骤"],
                risks=["自动转换可能不准确"],
                verification_policy="run_verify"
            )
        return None
    except Exception:
        return None

# ============================================================================
# 主要规划接口
# ============================================================================

def execute_planning_phase(
    loop,
    user_text: str,
    planning_prompt: str | None,
    trace_id: str,
    _ev: Callable[[str, dict[str, Any]], None],
    _llm_chat: Callable[[str, str | None], str],
) -> Plan | None:
    """执行规划阶段：生成显式 Plan。"""
    if not planning_prompt:
        return None

    logger = get_logger(
        __name__,
        workspace_root=loop.cfg.workspace_root,
        log_to_console=loop.cfg.logging.log_to_console,
        level=loop.cfg.logging.level,
        log_format=loop.cfg.logging.log_format,
        date_format=loop.cfg.logging.date_format,
    )

    logger.debug(f"[dim]进入规划阶段：生成显式 Plan[/dim]")
    
    plan_attempts = 0
    while plan_attempts <= loop.cfg.orchestrator.planning_retry:
        plan_attempts += 1
        _ev("planning_llm_request", {"attempt": plan_attempts})
        
        assistant_plan = _llm_chat("planning", None)
        _ev("planning_llm_response", {"text": assistant_plan[:4000], "truncated": len(assistant_plan) > 4000})
        
        # 🚨 修复：检测模型响应类型并提前处理对话式输出
        response_type = detect_model_response_type(assistant_plan)
        _ev("planning_response_type", {"type": response_type})
        
        # 如果是明显的错误类型，直接重试而不进行解析
        if response_type == 'conversational' and plan_attempts <= loop.cfg.orchestrator.planning_retry:
            logger.warning(f"⚠️ 检测到对话式响应，直接重试 (尝试 {plan_attempts}/{loop.cfg.orchestrator.planning_retry + 1})")
            # 添加针对性的重试消息到历史
            loop.messages.append(ChatMessage(
                role="user",
                content=f"请只输出JSON对象，格式要求: {{\"type\": \"FullPlan\", \"title\": \"任务标题\", \"steps\": [...]}}。不要任何解释文字。"
            ))
            loop._trim_history(max_messages=30)
            continue
        
        try:
            parsed = parse_plan_from_text(assistant_plan)
            if len(parsed.steps) > loop.cfg.orchestrator.max_plan_steps:
                parsed.steps = parsed.steps[: loop.cfg.orchestrator.max_plan_steps]
            plan = parsed

            # 强制校验步骤 ID 唯一性（parse_plan_from_text 已校验，这里做双保险）
            plan.validate_unique_ids()
            
            # 将 Plan 对象和内容添加到 audit
            loop.messages.append(ChatMessage(role="assistant", content=assistant_plan))
            loop._trim_history(max_messages=30)
            loop.audit.write(trace_id=trace_id, event="plan_generated", data={"title": plan.title, "steps": [s.model_dump() for s in plan.steps]})
            _ev("plan_generated", {"type": "FullPlan", "title": plan.title, "steps_count": len(plan.steps)})
            plan_summary = render_plan_markdown(plan)
            logger.info(f"[dim]计划摘要:\\n{plan_summary}[/dim]")
            return plan
        
        except (json.JSONDecodeError, ValueError, KeyError, AttributeError) as e:
            # 🚨 修复：基于响应类型提供更好的错误处理
            if response_type == 'conversational':
                # 对话式响应，需要重新引导模型输出JSON
                if plan_attempts <= loop.cfg.orchestrator.planning_retry:
                    logger.warning(f"⚠️ 模型输出对话式文字而非JSON，尝试重新引导 (尝试 {plan_attempts}/{loop.cfg.orchestrator.planning_retry + 1})")
                    # 添加特定的重试提示
                    loop.messages.append(ChatMessage(
                        role="user",
                        content=f"您刚才的输出是对话式文字，请输出纯JSON对象。格式要求: {{\"type\": \"FullPlan\", \"title\": \"任务标题\", \"steps\": [{{\"id\": \"step_1\", \"description\": \"具体动作\", \"expected_output\": \"预期结果\", \"dependencies\": [], \"tools_expected\": [\"工具名\"]}}]}}"
                    ))
                    loop._trim_history(max_messages=30)
                    continue
                else:
                    # 超过重试次数
                    error_detail = f"对话式响应无法纠正，尝试 {plan_attempts} 次"
                    logger.error(f"[red]✗ 计划解析失败 (尝试 {plan_attempts}/{loop.cfg.orchestrator.planning_retry + 1}): {error_detail}[/red]")
                    loop.audit.write(trace_id=trace_id, event="plan_parse_failed", data={"attempt": plan_attempts, "error": error_detail})
                    _ev("plan_parse_failed", {"attempt": plan_attempts, "error": error_detail})
                    return None
            
            # 尝试容错：检测是否为工具调用输出
            tool_call_plan = _try_convert_tool_call_to_plan(assistant_plan, loop)
            if tool_call_plan:
                # 成功转换，使用转换后的 Plan
                plan = tool_call_plan
                # 添加到历史
                loop.messages.append(ChatMessage(role="assistant", content=assistant_plan))
                loop._trim_history(max_messages=30)
                loop.audit.write(trace_id=trace_id, event="plan_generated_from_tool_call", data={"title": plan.title, "steps": [s.model_dump() for s in plan.steps]})
                _ev("plan_generated", {"type": "FullPlan", "title": plan.title, "steps_count": len(plan.steps)})
                logger.info("[green]✓ 计划生成成功（从工具调用转换）[/green]")
                plan_summary = render_plan_markdown(plan)
                logger.info(f"[dim]计划摘要:\\n{plan_summary}[/dim]")
                return plan
            
            # 无法容错，记录错误并重试
            error_detail = str(e) + f" [响应类型: {response_type}]"
            logger.error(f"[red]✗ 计划解析失败 (尝试 {plan_attempts}/{loop.cfg.orchestrator.planning_retry + 1}): {error_detail}[/red]", exc_info=True)
            loop.audit.write(trace_id=trace_id, event="plan_parse_failed", data={"attempt": plan_attempts, "error": error_detail})
            _ev("plan_parse_failed", {"attempt": plan_attempts, "error": error_detail})
            
            # 添加重试提示到历史
            retry_prompt = "您刚才的输出无法解析为有效的JSON计划。请只输出一个JSON对象，格式要求：{\"type\": \"FullPlan\", \"title\": \"任务标题\", \"steps\": [...]}"
            loop.messages.append(ChatMessage(role="user", content=retry_prompt))
            loop._trim_history(max_messages=30)
            
            # 如果超过最大重试次数，抛出异常
            if plan_attempts >= loop.cfg.orchestrator.planning_retry:
                raise ValueError(f"无法从模型输出中解析 Plan JSON。\\n最后错误: {error_detail}\\n响应类型: {response_type}")
            
            # 否则继续下一次重试
    
    # 如果达到最大重试次数仍失败，记录并返回 None
    logger.error(f"[red]✗ 达到最大重试次数，规划失败[/red]")
    return None

def render_plan_markdown(plan: Plan) -> str:
    """渲染 Plan 为 Markdown 格式"""
    lines = [
        f"**计划标题**: {plan.title}",
        f"**步骤数量**: {len(plan.steps)}",
        "**计划摘要:**"
    ]
    
    for i, step in enumerate(plan.steps, 1):
        deps = f" (deps: {', '.join(step.dependencies)})" if step.dependencies else ""
        tools = f" (tools: {', '.join(step.tools_expected)})" if step.tools_expected else ""
        lines.append(f"{i}. {step.description}{deps}{tools}")
    
    return "\\n".join(lines)

# ============================================================================
# 导出
# ============================================================================

__all__ = [
    "execute_planning_phase",
    "parse_plan_from_text",
    "render_plan_markdown"
]