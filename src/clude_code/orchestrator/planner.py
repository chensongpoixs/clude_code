from __future__ import annotations

import json
from typing import Any, List, Optional
from typing import Optional, List, Union;
from pydantic import BaseModel, Field, ValidationError


class PlanStep(BaseModel):
    """计划中的单个步骤。"""

    id: str = Field(..., description="步骤唯一 ID（如 step_1）")
    description: str = Field(..., description="步骤要做什么（尽量可执行、可验证）")
    dependencies: List[str] = Field(default_factory=list, description="依赖的步骤 id 列表")
    status: str = Field(default="pending", description="pending|in_progress|done|blocked|failed")
    tools_expected: List[str] = Field(default_factory=list, description="该步骤预计会用到的工具名列表")


class Plan(BaseModel):
    """显式计划（用于跨文件复杂任务的编排）。"""

    title: str = Field(..., description="任务全局目标")
    steps: List[PlanStep] = Field(..., min_length=1, description="步骤列表")
    verification_policy: Optional[str] = Field(
        default=None,
        description="验证策略（如 run_pytest / npm_test / go_test / cargo_test）。可为空，由编排层决定。",
    )

    def get_ready_steps(self, completed_ids: set[str]) -> List[PlanStep]:
        """返回所有依赖已满足且状态为 pending 的步骤（用于依赖调度）。"""
        ready = []
        for s in self.steps:
            if s.status == "pending" and all(dep in completed_ids for dep in s.dependencies):
                ready.append(s)
        return ready

    def validate_unique_ids(self) -> None:
        """校验步骤 ID 唯一性，重复则抛 ValueError。"""
        ids = [s.id for s in self.steps]
        if len(ids) != len(set(ids)):
            dups = [x for x in ids if ids.count(x) > 1]
            raise ValueError(f"步骤 ID 重复: {set(dups)}")


#def _extract_json_candidates(text: str) -> List[str]:
def _extract_json_candidates(text: Optional[Union[str, bytes]]) -> List[str]:
    """
    从 LLM 输出中提取可能的 JSON 对象字符串候选。
    - 允许夹杂解释文本
    - 允许 fenced code block
    """

    if isinstance(text, bytes):
        text = text.decode('utf-8')
    elif text is None:
        text = ""
    elif not isinstance(text, str):
        raise TypeError(f"_extract_json_candidates Expected str, got {type(text).__name__}")
    # 后续代码...
    t = (text or "").strip()
    cands: List[str] = []
    if t.startswith("{") and t.endswith("}"):
        cands.append(t)
    if "```" in t:
        for fence in ("```json", "```JSON", "```"):
            if fence in t:
                parts = t.split(fence, 1)
                if len(parts) == 2:
                    body = parts[1].split("```", 1)[0].strip()
                    if body.startswith("{") and body.endswith("}"):
                        cands.append(body)
    if "{" in t and "}" in t:
        start = t.find("{")
        end = t.rfind("}")
        if 0 <= start < end:
            cands.append(t[start : end + 1].strip())
    # 去重保持顺序
    seen = set()
    out: List[str] = []
    for s in cands:
        if s not in seen:
            out.append(s)
            seen.add(s)
    return out


def parse_plan_from_text(text: str) -> Plan:
    """
    从 LLM 文本中解析 Plan。
    失败会抛出 ValueError（包含原因摘要），上层可触发重试或降级。
    """
    candidates = _extract_json_candidates(text)
    last_err: str | None = None
    for c in candidates:
        try:
            obj = json.loads(c)
            if not isinstance(obj, dict):
                continue
            plan = Plan.model_validate(obj)
            # 额外校验：步骤 ID 唯一性
            plan.validate_unique_ids()
            return plan
        except (json.JSONDecodeError, ValidationError, ValueError) as e:
            last_err = str(e) + "[ candidates: " + str([c for c in candidates]) + "]";
            continue
    raise ValueError(f"无法从模型输出中解析 Plan JSON。{('最后错误: ' + last_err) if last_err else ''}")


def render_plan_markdown(plan: Plan) -> str:
    """用于日志/审计展示的计划渲染（不作为模型输入契约）。"""
    lines: List[str] = []
    lines.append(f"计划标题: {plan.title}")
    for i, s in enumerate(plan.steps, start=1):
        deps = ", ".join(s.dependencies) if s.dependencies else "-"
        tools = ", ".join(s.tools_expected) if s.tools_expected else "-"
        lines.append(f"{i}. {s.id} [{s.status}] {s.description} (deps: {deps}; tools: {tools})")
    if plan.verification_policy:
        lines.append(f"验证策略: {plan.verification_policy}")
    return "\n".join(lines)


