"""
P0-3 Plan Patching 最小回归用例 (Regression Tests for Plan Patching / 计划补丁回归测试)

本测试模块用于验证 P0-3 局部重规划功能的核心健壮性。

验证场景：
1. done 步骤保护：已完成步骤不被修改/删除，且不被重复执行
2. 依赖校验：新增/更新步骤的依赖必须指向存在的 step_id
3. 超限截断：新增步骤超过 max_plan_steps 时会被截断并记录

业界对齐：
- Claude Code / Aider / OpenCode 均有类似"局部修补优先"策略
- 已完成步骤不可变是业界共识（避免逻辑不一致）

运行方式：
    conda run -n claude_code python -m pytest tests/test_plan_patching.py -v

符合规范：
- docs/CODE_SPECIFICATION.md 5.1 单元测试
- docs/22-plan-patching.md 验收标准
"""

import pytest

from clude_code.orchestrator.planner import (
    Plan,
    PlanStep,
    PlanPatch,
    PlanStepUpdate,
    parse_plan_patch_from_text,
    apply_plan_patch,
)


# =============================================================================
# 辅助说明（中文注释）：
# - Plan: 完整计划对象，包含 title + steps
# - PlanStep: 单个步骤，包含 id/description/dependencies/status/tools_expected
# - PlanPatch: 增量补丁，包含 remove_steps/update_steps/add_steps
# - PlanStepUpdate: 步骤更新描述，只允许更新 description/dependencies/tools_expected
# =============================================================================


# ---------------------------------------------------------------------------
# 测试 1: done 步骤保护 (Done Steps Protection / 已完成步骤保护)
# ---------------------------------------------------------------------------
class TestDoneStepsPreserved:
    """
    验证 apply_plan_patch 对已完成步骤的保护机制。
    
    业界规范：已完成步骤是只读的（immutable），不允许修改或删除。
    原因：
    - 避免逻辑不一致（已完成的工作被撤销）
    - 避免重复执行（浪费 Token 且可能产生副作用）
    """

    def test_done_step_status_preserved(self):
        """已完成步骤的状态应保留，不被 patch 覆盖。"""
        # 原 Plan：step_1 已 done，step_2 pending
        original = Plan(
            title="原始计划",
            steps=[
                PlanStep(id="step_1", description="读取文件", status="done"),
                PlanStep(id="step_2", description="分析代码", status="pending"),
            ],
        )

        # Patch：更新 step_2 的描述（但不动 step_1）
        patch = PlanPatch(
            update_steps=[
                PlanStepUpdate(id="step_2", description="分析代码（更新后）"),
            ],
        )

        new_plan, meta = apply_plan_patch(original, patch, max_plan_steps=10)

        # step_1 应仍为 done
        assert new_plan.steps[0].id == "step_1"
        assert new_plan.steps[0].status == "done"

        # step_2 描述被更新
        assert new_plan.steps[1].id == "step_2"
        assert "更新后" in new_plan.steps[1].description

    def test_update_done_step_raises(self):
        """禁止更新 done 步骤（符合业界实践：已完成步骤是只读的）。"""
        original = Plan(
            title="原始计划",
            steps=[
                PlanStep(id="step_1", description="旧描述", status="done"),
            ],
        )

        patch = PlanPatch(
            update_steps=[
                PlanStepUpdate(id="step_1", description="新描述"),
            ],
        )

        with pytest.raises(ValueError) as exc_info:
            apply_plan_patch(original, patch, max_plan_steps=10)

        assert "step_1" in str(exc_info.value)
        assert "done" in str(exc_info.value).lower() or "禁止" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 测试 2: 依赖校验 (Dependency Validation / 依赖校验)
# ---------------------------------------------------------------------------
class TestDependencyValidation:
    """
    验证依赖校验机制：引用不存在的 step_id 会抛 ValueError。
    
    业界规范：依赖必须指向存在的 step_id，否则执行器会陷入死锁。
    校验时机：apply_plan_patch() 应用补丁后立即校验。
    """

    def test_add_step_with_invalid_dependency_raises(self):
        """新增步骤依赖不存在的 step_id，应抛 ValueError。"""
        original = Plan(
            title="原始计划",
            steps=[
                PlanStep(id="step_1", description="第一步", status="done"),
            ],
        )

        # 新增 step_2 依赖不存在的 step_999
        patch = PlanPatch(
            add_steps=[
                PlanStep(id="step_2", description="新步骤", dependencies=["step_999"]),
            ],
        )

        with pytest.raises(ValueError) as exc_info:
            apply_plan_patch(original, patch, max_plan_steps=10)

        assert "step_999" in str(exc_info.value)
        assert "不存在" in str(exc_info.value) or "invalid" in str(exc_info.value).lower()

    def test_add_step_with_valid_dependency_ok(self):
        """新增步骤依赖存在的 step_id，应正常应用。"""
        original = Plan(
            title="原始计划",
            steps=[
                PlanStep(id="step_1", description="第一步", status="done"),
            ],
        )

        patch = PlanPatch(
            add_steps=[
                PlanStep(id="step_2", description="新步骤", dependencies=["step_1"]),
            ],
        )

        new_plan, meta = apply_plan_patch(original, patch, max_plan_steps=10)

        assert len(new_plan.steps) == 2
        assert new_plan.steps[1].id == "step_2"
        assert new_plan.steps[1].dependencies == ["step_1"]


# ---------------------------------------------------------------------------
# 测试 3: 超限截断 (Max Steps Truncation / 超限截断)
# ---------------------------------------------------------------------------
class TestMaxStepsTruncation:
    """
    验证新增步骤超过 max_plan_steps 时的截断机制。
    
    业界规范：计划步骤数应有上限（避免无限膨胀导致 Token 爆炸）。
    截断策略：只截断新增步骤（不影响已有步骤），并在 meta 中记录 truncated_add=True。
    """

    def test_add_exceeds_max_steps_truncated(self):
        """新增步骤导致总数超限时，只保留 max_steps 步，并记录 truncated_add。"""
        original = Plan(
            title="原始计划",
            steps=[
                PlanStep(id="step_1", description="第一步", status="done"),
                PlanStep(id="step_2", description="第二步", status="pending"),
            ],
        )

        # 尝试新增 5 步，但 max_steps=4，只能再加 2 步
        patch = PlanPatch(
            add_steps=[
                PlanStep(id="step_3", description="新步骤 3"),
                PlanStep(id="step_4", description="新步骤 4"),
                PlanStep(id="step_5", description="新步骤 5"),
                PlanStep(id="step_6", description="新步骤 6"),
                PlanStep(id="step_7", description="新步骤 7"),
            ],
        )

        new_plan, meta = apply_plan_patch(original, patch, max_plan_steps=4)

        # 总步骤数应为 4
        assert len(new_plan.steps) == 4

        # 发生了截断（布尔标志）
        assert meta.get("truncated_add") is True

        # 验证保留的步骤
        ids = [s.id for s in new_plan.steps]
        assert "step_1" in ids
        assert "step_2" in ids
        assert "step_3" in ids
        assert "step_4" in ids
        assert "step_5" not in ids  # 被截断
        assert "step_6" not in ids  # 被截断
        assert "step_7" not in ids  # 被截断

    def test_no_truncation_when_within_limit(self):
        """新增步骤未超限时，不应有 truncated_add。"""
        original = Plan(
            title="原始计划",
            steps=[
                PlanStep(id="step_1", description="第一步", status="done"),
            ],
        )

        patch = PlanPatch(
            add_steps=[
                PlanStep(id="step_2", description="新步骤 2"),
            ],
        )

        new_plan, meta = apply_plan_patch(original, patch, max_plan_steps=10)

        assert len(new_plan.steps) == 2
        assert meta.get("truncated_add", 0) == 0


# ---------------------------------------------------------------------------
# 测试 4: 解析器隔离 (Parser Isolation / 解析器隔离)
# ---------------------------------------------------------------------------
class TestPatchParsing:
    """
    验证 parse_plan_patch_from_text 正确解析 PlanPatch，且不误解析 full Plan。
    
    业界规范：PlanPatch 与 full Plan 必须严格区分，防止误判。
    实现方式：PlanPatch 模型使用 extra="forbid"，拒绝包含 steps 字段的输入。
    """

    def test_parse_valid_patch(self):
        """合法的 PlanPatch JSON 应正确解析。"""
        text = '''
        {
            "update_steps": [
                {"id": "step_1", "description": "更新描述"}
            ],
            "add_steps": [
                {"id": "step_3", "description": "新步骤"}
            ]
        }
        '''
        patch = parse_plan_patch_from_text(text)

        assert len(patch.update_steps or []) == 1
        assert (patch.update_steps or [])[0].id == "step_1"
        assert len(patch.add_steps or []) == 1
        assert (patch.add_steps or [])[0].id == "step_3"

    def test_parse_full_plan_raises(self):
        """full Plan JSON（含 title + steps）不应被误解析为 PlanPatch。"""
        text = '''
        {
            "title": "这是一个完整计划",
            "steps": [
                {"id": "step_1", "description": "第一步"}
            ]
        }
        '''
        with pytest.raises(ValueError):
            parse_plan_patch_from_text(text)


# ---------------------------------------------------------------------------
# 测试 5: 删除步骤 (Delete Steps / 删除步骤)
# ---------------------------------------------------------------------------
class TestDeleteSteps:
    """
    验证删除步骤功能（remove_steps）。
    
    业界规范：
    - 允许删除 pending/blocked/failed 步骤
    - 禁止删除 done 步骤（已完成步骤不可变）
    """

    def test_delete_pending_step(self):
        """删除 pending 步骤应成功。"""
        original = Plan(
            title="原始计划",
            steps=[
                PlanStep(id="step_1", description="第一步", status="done"),
                PlanStep(id="step_2", description="第二步", status="pending"),
                PlanStep(id="step_3", description="第三步", status="pending"),
            ],
        )

        patch = PlanPatch(remove_steps=["step_2"])

        new_plan, meta = apply_plan_patch(original, patch, max_plan_steps=10)

        assert len(new_plan.steps) == 2
        ids = [s.id for s in new_plan.steps]
        assert "step_1" in ids
        assert "step_2" not in ids
        assert "step_3" in ids

    def test_delete_done_step_raises(self):
        """禁止删除 done 步骤（符合业界实践：已完成步骤是只读的）。"""
        original = Plan(
            title="原始计划",
            steps=[
                PlanStep(id="step_1", description="第一步", status="done"),
                PlanStep(id="step_2", description="第二步", status="pending"),
            ],
        )

        patch = PlanPatch(remove_steps=["step_1"])

        with pytest.raises(ValueError) as exc_info:
            apply_plan_patch(original, patch, max_plan_steps=10)

        assert "step_1" in str(exc_info.value)
        assert "done" in str(exc_info.value).lower() or "禁止" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 运行入口
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    pytest.main([__file__, "-v"])

