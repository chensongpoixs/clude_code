from __future__ import annotations

"""
计划与补丁模块（Planner Module / 计划与补丁模块）

模块职责 (Module Responsibility)：
- 定义 Plan、PlanStep、PlanPatch 等核心数据模型
- 提供计划解析、补丁应用、状态同步等核心功能
- 支持增量重规划（PlanPatch）和全量重规划（Full Plan）两种模式

设计原则 (Design Principles)：
1. 已完成步骤不可变（Done Steps Immutable）：禁止删除/修改 status=done 的步骤
2. 依赖一致性（Dependency Consistency）：所有 dependencies 必须指向存在的 step_id
3. 容量控制（Capacity Control）：步骤数不超过 max_plan_steps，超限时截断新增部分
4. 可回退（Fallback）：补丁解析失败时允许回退到全量计划解析

业界对齐 (Industry Alignment)：
- Claude Code / Aider / OpenCode 均有"局部修补优先"策略
- 增量重规划降低 Token 成本，避免上下文丢失

使用示例 (Usage Example)：
    >>> from clude_code.orchestrator.planner import Plan, PlanPatch, apply_plan_patch
    >>> plan = Plan(title="示例", steps=[PlanStep(id="s1", description="读取文件")])
    >>> patch = PlanPatch(add_steps=[PlanStep(id="s2", description="分析代码")])
    >>> new_plan, meta = apply_plan_patch(plan, patch, max_plan_steps=10)
"""

import json
from typing import Any, Dict, List, Optional, Set, Union, Literal
from pydantic import BaseModel, Field, ValidationError


class PlanStep(BaseModel):
    """
    计划步骤（Plan Step / 计划步骤）。
    
    表示计划中的单个可执行步骤，包含描述、依赖、状态和预期工具。
    
    Attributes:
        id: 步骤唯一标识（如 step_1）
        description: 步骤要做什么（尽量可执行、可验证）
        dependencies: 依赖的步骤 id 列表（必须全部完成才能执行本步骤）
        status: 状态（pending/in_progress/done/blocked/failed）
        tools_expected: 预计会用到的工具名列表（用于提示）
    """

    id: str = Field(..., description="步骤唯一 ID（如 step_1）")
    description: str = Field(..., description="步骤要做什么（尽量可执行、可验证）")
    dependencies: List[str] = Field(default_factory=list, description="依赖的步骤 id 列表")
    status: str = Field(default="pending", description="pending|in_progress|done|blocked|failed")
    tools_expected: List[str] = Field(default_factory=list, description="该步骤预计会用到的工具名列表")


class Plan(BaseModel):
    """
    显式计划（Explicit Plan / 显式计划）。
    
    用于跨文件复杂任务的编排，包含标题、步骤列表和验证策略。
    
    Attributes:
        title: 任务全局目标
        steps: 步骤列表（至少 1 步）
        verification_policy: 验证策略（如 run_pytest / npm_test）
    """

    type: Literal["FullPlan"] = Field(default="FullPlan", description="输出类型标识：FullPlan")
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


class PlanStepUpdate(BaseModel):
    """
    步骤更新描述（Plan Step Update / 步骤更新描述）。
    
    用于 PlanPatch 中描述对某个步骤的增量更新。
    不允许直接修改 status（由执行器管理）。
    
    Attributes:
        id: 要更新的 step_id（必填）
        description: 可选，更新描述
        dependencies: 可选，更新依赖列表（全量覆盖）
        tools_expected: 可选，更新预计工具列表（全量覆盖）
    """

    model_config = {"extra": "forbid"}  # 禁止额外字段，防止误解析 full Plan

    id: str = Field(..., description="要更新的 step_id")
    description: Optional[str] = Field(default=None, description="可选：更新描述")
    dependencies: Optional[List[str]] = Field(default=None, description="可选：更新依赖列表（全量覆盖）")
    tools_expected: Optional[List[str]] = Field(default=None, description="可选：更新预计工具列表（全量覆盖）")


class PlanPatch(BaseModel):
    """
    计划补丁（Plan Patch / 计划补丁）。
    
    只描述"增量变化"，避免全量重写 Plan，降低 Token 成本和上下文丢失风险。
    
    业界做法：Claude Code / Aider / OpenCode 等优先使用局部修补策略。
    
    Attributes:
        title: 可选，更新计划标题
        remove_steps: 要删除的 step_id 列表（禁止删除 done 步骤）
        update_steps: 要更新的步骤列表（禁止更新 done 步骤）
        add_steps: 要新增的步骤（会被强制设为 pending）
        reason: 可选，为什么这样 patch（用于可观测性）
        
    JSON 示例：
        {
            "update_steps": [{"id": "step_3", "description": "新描述"}],
            "add_steps": [{"id": "step_4", "description": "新步骤"}],
            "reason": "步骤 3 失败，需要调整方案"
        }
    """

    model_config = {"extra": "forbid"}  # 禁止额外字段，防止误解析 full Plan

    type: Literal["PlanPatch"] = Field(default="PlanPatch", description="输出类型标识：PlanPatch")
    title: Optional[str] = Field(default=None, description="可选：更新计划标题")
    remove_steps: List[str] = Field(default_factory=list, description="要删除的 step_id 列表（禁止删除 done）")
    update_steps: List[PlanStepUpdate] = Field(default_factory=list, description="要更新的步骤列表（禁止更新 done）")
    add_steps: List[PlanStep] = Field(default_factory=list, description="要新增的步骤（会被强制设为 pending）")
    reason: Optional[str] = Field(default=None, description="可选：为什么这样 patch（用于可观测性）")


def parse_plan_patch_from_text(text: str) -> PlanPatch:
    """
    从 LLM 文本中解析 PlanPatch（计划补丁）。
    
    解析策略：
    1. 提取 JSON 候选（支持 fenced code block）
    2. 尝试 Pydantic 校验（extra="forbid" 会拒绝包含 steps 的 full Plan）
    3. 失败抛 ValueError，上层可回退解析 full Plan
    
    Args:
        text: LLM 输出的原始文本
        
    Returns:
        PlanPatch: 解析成功时返回计划补丁
        
    Raises:
        ValueError: 解析失败时抛出，包含最后一个错误信息
    """
    candidates = _extract_json_candidates(text)
    last_err: str | None = None
    for c in candidates:
        try:
            obj = json.loads(c)
            if not isinstance(obj, dict):
                continue
            patch = PlanPatch.model_validate(obj)
            return patch
        except (json.JSONDecodeError, ValidationError, ValueError) as e:
            last_err = str(e)
            continue
    raise ValueError(f"无法从模型输出中解析 PlanPatch JSON。{('最后错误: ' + last_err) if last_err else ''}")


def _index_steps(plan: Plan) -> Dict[str, PlanStep]:
    """构建 step_id -> PlanStep 的索引，用于快速查找。"""
    return {s.id: s for s in plan.steps}


def _validate_dependencies_exist(plan: Plan) -> None:
    """
    校验所有步骤的依赖是否存在。
    
    如果某个步骤的 dependencies 包含不存在的 step_id，抛出 ValueError。
    """
    ids: Set[str] = {s.id for s in plan.steps}
    missing: Dict[str, List[str]] = {}
    for s in plan.steps:
        miss = [d for d in (s.dependencies or []) if d not in ids]
        if miss:
            missing[s.id] = miss
    if missing:
        raise ValueError(f"存在不存在的依赖 step_id: {missing}")

"""
对 Plan 应用 PlanPatch（计划补丁），返回新计划和元数据。

应用顺序：
1. 删除步骤（remove_steps）：禁止删除 done 步骤
2. 更新步骤（update_steps）：禁止更新 done 步骤
3. 新增步骤（add_steps）：强制设为 pending，超限截断
4. 校验：唯一 ID + 依赖存在

Args:
    plan: 原始计划
    patch: 计划补丁
    max_plan_steps: 最大步骤数限制
    
Returns:
    tuple: (new_plan, meta)
    - new_plan: 应用补丁后的新计划
    - meta: 元数据 {"added": int, "updated": int, "removed": int, "truncated_add": bool}
    
Raises:
    ValueError: 违反约束时抛出（删除/更新 done 步骤、依赖不存在等）
"""
def apply_plan_patch(
    plan: Plan,
    patch: PlanPatch,
    *,
    max_plan_steps: int,
) -> tuple[Plan, dict[str, Any]]:

    if max_plan_steps <= 0:
        raise ValueError("max_plan_steps 必须为正整数")

    new_plan = plan.model_copy(deep=True)
    meta: dict[str, Any] = {"added": 0, "updated": 0, "removed": 0, "truncated_add": False}

    # P0-3: 防御性校验——避免出现“同一步骤既删除又更新/新增”的冲突补丁
    rm_ids = set([str(x).strip() for x in (patch.remove_steps or []) if str(x).strip()])
    up_ids = set([str(u.id).strip() for u in (patch.update_steps or []) if str(getattr(u, "id", "")).strip()])
    add_ids = set([str(s.id).strip() for s in (patch.add_steps or []) if str(getattr(s, "id", "")).strip()])
    conflict_rm_up = sorted(list(rm_ids & up_ids))
    conflict_rm_add = sorted(list(rm_ids & add_ids))
    conflict_up_add = sorted(list(up_ids & add_ids))
    if conflict_rm_up or conflict_rm_add or conflict_up_add:
        raise ValueError(
            "PlanPatch 内部冲突：同一步骤不能同时出现在 remove_steps/update_steps/add_steps 中。"
            f" rm∩update={conflict_rm_up} rm∩add={conflict_rm_add} update∩add={conflict_up_add}"
        )

    if patch.title is not None and str(patch.title).strip():
        new_plan.title = str(patch.title).strip()

    # 1) 删除（禁止删除 done）
    if patch.remove_steps:
        rm = set([str(x).strip() for x in patch.remove_steps if str(x).strip()])
        kept: List[PlanStep] = []
        for s in new_plan.steps:
            if s.id in rm:
                if s.status == "done":
                    raise ValueError(f"禁止删除已完成步骤: {s.id}")
                meta["removed"] += 1
                continue
            kept.append(s)
        new_plan.steps = kept

    # 2) 更新（禁止更新 done）
    if patch.update_steps:
        idx = _index_steps(new_plan)
        for u in patch.update_steps:
            sid = str(u.id).strip()
            if not sid:
                continue
            if sid not in idx:
                raise ValueError(f"要更新的 step_id 不存在: {sid}")
            s = idx[sid]
            if s.status == "done":
                raise ValueError(f"禁止更新已完成步骤: {sid}")
            if u.description is not None:
                s.description = str(u.description)
            if u.dependencies is not None:
                s.dependencies = list(u.dependencies)
            if u.tools_expected is not None:
                s.tools_expected = list(u.tools_expected)
            meta["updated"] += 1

    # 3) 新增（强制 pending；超限则截断新增部分并标记）
    add_steps: List[PlanStep] = []
    for s in patch.add_steps or []:
        ss = s.model_copy(deep=True)
        ss.status = "pending"
        add_steps.append(ss)

    # 先做一次唯一性预检查，避免后续 validate_unique_ids 报错信息不清晰
    existing_ids = {s.id for s in new_plan.steps}
    for s in add_steps:
        if s.id in existing_ids:
            raise ValueError(f"新增步骤 step_id 与现有冲突: {s.id}")
        existing_ids.add(s.id)

    # 容量控制：只截断新增部分
    capacity = max_plan_steps - len(new_plan.steps)
    if capacity < 0:
        # 旧计划本身就超限：不在这里强制裁剪（避免破坏已完成信息）
        raise ValueError(f"当前 plan.steps 已超过 max_plan_steps: {len(new_plan.steps)}/{max_plan_steps}")
    if len(add_steps) > capacity:
        add_steps = add_steps[:capacity]
        meta["truncated_add"] = True
    new_plan.steps.extend(add_steps)
    meta["added"] = len(add_steps)

    # 4) 校验：唯一 ID + 依赖存在
    new_plan.validate_unique_ids()
    _validate_dependencies_exist(new_plan)
    return new_plan, meta


def carry_over_done_status(old_plan: Plan, new_plan: Plan) -> Plan:
    """
    在全量重规划回退路径中，保留已完成步骤的 done 状态。
    
    当 PlanPatch 解析失败回退到 full Plan 时，使用此函数同步 done 状态，
    避免已完成的步骤被重复执行。
    
    规则：同 id 的 step，若 old 为 done，则 new 也标为 done。
    
    Args:
        old_plan: 旧计划（包含 done 状态信息）
        new_plan: 新计划（来自 full Plan 解析）
        
    Returns:
        Plan: 状态同步后的新计划
    """
    done_ids = {s.id for s in old_plan.steps if s.status == "done"}
    if not done_ids:
        return new_plan
    for s in new_plan.steps:
        if s.id in done_ids:
            s.status = "done"
    return new_plan


def _extract_json_candidates(text: Optional[Union[str, bytes]]) -> List[str]:
    """
    从 LLM 输出中提取可能的 JSON 对象字符串候选。
    
    支持的格式：
    - 纯 JSON 对象（以 `{` 开头，`}` 结尾）
    - Fenced code block（```json ... ``` 或 ``` ... ```）
    - 夹杂在解释文本中的 JSON（提取第一个 `{` 到最后一个 `}`）
    
    Args:
        text: LLM 输出的原始文本（支持 str/bytes/None）
        
    Returns:
        List[str]: JSON 候选字符串列表（去重、保持顺序）
    """
    # 类型归一化：bytes -> str, None -> ""
    if isinstance(text, bytes):
        text = text.decode('utf-8')
    elif text is None:
        text = ""
    elif not isinstance(text, str):
        raise TypeError(f"_extract_json_candidates Expected str, got {type(text).__name__}")
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
    从 LLM 文本中解析 Plan（完整计划）。
    
    解析策略：
    1. 提取 JSON 候选（支持 fenced code block）
    2. 尝试 Pydantic 校验
    3. 额外校验步骤 ID 唯一性
    4. 失败抛 ValueError（包含原因摘要），上层可触发重试或降级
    
    Args:
        text: LLM 输出的原始文本
        
    Returns:
        Plan: 解析成功时返回完整计划
        
    Raises:
        ValueError: 解析失败时抛出，包含最后一个错误信息
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
    """
    将 Plan 渲染为 Markdown 格式（用于日志/审计展示）。
    
    注意：此函数仅用于人类可读展示，不作为模型输入契约。
    """
    lines: List[str] = []
    lines.append(f"计划标题: {plan.title}")
    for i, s in enumerate(plan.steps, start=1):
        deps = ", ".join(s.dependencies) if s.dependencies else "-"
        tools = ", ".join(s.tools_expected) if s.tools_expected else "-"
        lines.append(f"{i}. {s.id} [{s.status}] {s.description} (deps: {deps}; tools: {tools})")
    if plan.verification_policy:
        lines.append(f"验证策略: {plan.verification_policy}")
    return "\n".join(lines)


