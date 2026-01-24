# Phase 2: planning.py 添加工具调用容错

> **目标**: 当 LLM 误输出工具调用时，自动转换为 Plan
> **状态**: 🔄 进行中

---

## 1. 思考过程

### 1.1 容错策略

即使 Prompt 已经明确约束，LLM 仍可能输出工具调用。需要添加"Plan B"：

**检测 → 转换 → 继续**
```
LLM 输出: {"tool": "xxx", "args": {...}}
  ↓
检测: 这是工具调用，不是 Plan
  ↓
转换: 包装为单步 Plan
  ↓
继续: 正常执行流程
```

### 1.2 转换逻辑

```python
if "tool" in output and "args" in output and "type" not in output:
    # 检测到工具调用
    tool_name = output["tool"]
    tool_args = output["args"]
    
    # 转换为单步 Plan
    plan = {
        "type": "FullPlan",
        "title": f"执行 {tool_name} 工具",
        "steps": [
            {
                "id": "step_1",
                "description": f"调用 {tool_name}",
                "dependencies": [],
                "tools_expected": [tool_name],
                "status": "pending"
            }
        ]
    }
```

---

## 2. 实现方案

### 2.1 修改位置

**文件**: `src/clude_code/orchestrator/agent_loop/planning.py`

**函数**: `execute_planning_phase`

**位置**: 在 `parse_plan_from_text` 失败后，尝试容错

### 2.2 实现代码

```python
# 在 parse_plan_from_text 抛出异常后
except ValueError as e:
    # 尝试容错：检测是否为工具调用
    tool_call_plan = _try_convert_tool_call_to_plan(assistant_plan, loop)
    if tool_call_plan:
        loop.logger.warning(
            f"[Planning] 检测到工具调用输出，已自动转换为 Plan: "
            f"{tool_call_plan.steps[0].description}"
        )
        plan = tool_call_plan
    else:
        # 无法容错，抛出原始错误
        raise
```

### 2.3 辅助函数

```python
def _try_convert_tool_call_to_plan(
    text: str,
    loop: Any
) -> Plan | None:
    """
    尝试将工具调用 JSON 转换为 Plan。
    
    检测模式:
    - {"tool": "xxx", "args": {...}}
    - {"tool": "xxx", "params": {...}}
    
    Returns:
        Plan 对象或 None（无法转换）
    """
    import json
    from clude_code.orchestrator.planner import Plan, Step
    
    try:
        # 解析 JSON
        data = json.loads(text)
        
        # 检测是否为工具调用
        if not isinstance(data, dict):
            return None
        
        tool_name = data.get("tool")
        if not tool_name:
            return None
        
        # 检查是否有 args/params
        if "args" not in data and "params" not in data:
            return None
        
        # 构建单步 Plan
        step = Step(
            id="step_1",
            description=f"使用 {tool_name} 工具",
            dependencies=[],
            tools_expected=[tool_name],
            status="pending"
        )
        
        plan = Plan(
            type="FullPlan",
            title=f"执行 {tool_name}",
            steps=[step]
        )
        
        return plan
    except Exception:
        return None
```

---

## 3. 修改清单

| 文件 | 修改内容 | 行数 |
| :--- | :--- | :--- |
| `planning.py` | 添加 `_try_convert_tool_call_to_plan` 函数 | +40 |
| `planning.py` | 在 `execute_planning_phase` 添加容错逻辑 | +10 |

---

## 4. 预期效果

### Before（修改前）
```
LLM 输出: {"tool": "analyze_image", ...}
结果: ❌ ValueError: 无法解析 Plan JSON
流程: 中断
```

### After（修改后）
```
LLM 输出: {"tool": "analyze_image", ...}
检测: 工具调用格式
转换: 单步 Plan
结果: ✅ 继续执行
日志: [Planning] 检测到工具调用输出，已自动转换为 Plan
```

---

## 5. 边界条件

### 5.1 有效的工具调用
```json
{"tool": "grep", "args": {"pattern": "..."}}
```
→ ✅ 转换为 Plan

### 5.2 无效的工具调用
```json
{"tool": "invalid_tool", "args": {}}
```
→ ✅ 转换为 Plan（工具验证在执行阶段）

### 5.3 非工具调用格式
```json
{"title": "...", "steps": [...]}  // 缺少 type 字段
```
→ ❌ 返回 None，抛出原始错误

---

## 6. 风险评估

| 风险 | 概率 | 影响 | 缓解措施 |
| :--- | :--- | :--- | :--- |
| 误判正常输出 | 低 | 中 | 严格检测条件 |
| 工具名称无效 | 低 | 低 | 执行阶段会检测 |
| 破坏现有逻辑 | 低 | 高 | 只在 ValueError 后触发 |

---

## 7. 测试用例

### 测试 1: 工具调用转换
```python
text = '{"tool": "grep", "args": {"pattern": "test"}}'
plan = _try_convert_tool_call_to_plan(text, loop)
assert plan is not None
assert plan.steps[0].tools_expected == ["grep"]
```

### 测试 2: 非工具调用
```python
text = '{"title": "Test", "steps": []}'
plan = _try_convert_tool_call_to_plan(text, loop)
assert plan is None
```

### 测试 3: 无效 JSON
```python
text = 'not json'
plan = _try_convert_tool_call_to_plan(text, loop)
assert plan is None
```

---

## 8. 实施步骤

1. [ ] 读取 `planning.py` 当前代码
2. [ ] 添加 `_try_convert_tool_call_to_plan` 函数
3. [ ] 修改 `execute_planning_phase` 添加容错逻辑
4. [ ] 编译检查
5. [ ] 单元测试
6. [ ] 集成测试

