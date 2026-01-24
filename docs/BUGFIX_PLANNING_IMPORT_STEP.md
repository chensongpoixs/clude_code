# Bug Fix: planning.py 导入错误

> **问题**: ImportError: cannot import name 'Step' from 'clude_code.orchestrator.planner'
> **原因**: Step 类实际名称为 PlanStep
> **状态**: ✅ 已修复

---

## 1. 问题分析

### 1.1 错误堆栈
```python
File "planning.py", line 7
from clude_code.orchestrator.planner import parse_plan_from_text, render_plan_markdown, Plan, Step
ImportError: cannot import name 'Step' from 'clude_code.orchestrator.planner'
```

### 1.2 根本原因

在 Phase 2 修改中，错误地使用了 `Step` 类名：
```python
from clude_code.orchestrator.planner import ..., Step  # ❌ 错误
```

但 `planner.py` 中的类名是 `PlanStep`：
```python
class PlanStep(BaseModel):
    """计划步骤"""
```

---

## 2. 诊断过程

### 2.1 查找 Step 类定义
```bash
grep "class.*Step" planner.py
# 结果: class PlanStep(BaseModel)
```

### 2.2 确认类名
- ❌ `Step` - 不存在
- ✅ `PlanStep` - 正确的类名

---

## 3. 解决方案

### 修改 planning.py

**修改 1: 导入语句**
```python
# Before
from clude_code.orchestrator.planner import ..., Step

# After
from clude_code.orchestrator.planner import ..., PlanStep
```

**修改 2: 使用位置**
```python
# Before
step = Step(...)

# After
step = PlanStep(...)
```

---

## 4. 修复验证

### 4.1 编译检查
```bash
python -m compileall planning.py
✅ 通过
```

### 4.2 导入测试
```python
from clude_code.orchestrator.agent_loop.planning import execute_planning_phase, _try_convert_tool_call_to_plan
✅ 导入成功
```

---

## 5. 修复总结

| 项目 | 修改前 | 修改后 |
| :--- | :--- | :--- |
| **导入** | `import Step` | `import PlanStep` |
| **实例化** | `Step(...)` | `PlanStep(...)` |
| **编译** | ❌ ImportError | ✅ 通过 |
| **导入测试** | ❌ 失败 | ✅ 成功 |

---

## 6. 经验总结

### 问题根源
- 未仔细检查目标模块的实际类名
- 假设类名简化（`Step` vs `PlanStep`）

### 预防措施
1. **修改前验证**: 先 grep 查找类名
2. **IDE 辅助**: 使用 IDE 的自动补全
3. **及时测试**: 修改后立即编译检查

