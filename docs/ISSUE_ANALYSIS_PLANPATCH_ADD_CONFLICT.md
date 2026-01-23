# PlanPatch add_steps 与现有计划冲突问题分析

> **分析日期**: 2026-01-23  
> **问题级别**: 🔴 严重（阻塞执行）

---

## 1. 问题现象

### 1.1 错误日志
```
[PlanPatch] 自动纠正：从 remove_steps 移除 ['step_6']（保留 add）
✗ 重规划解析失败 patch_error=新增步骤 step_id 与现有冲突: step_6
```

### 1.2 LLM 返回的 JSON
```json
{
  "type": "PlanPatch",
  "remove_steps": ["step_6"],      // ← 想删除 step_6
  "add_steps": [
    {
      "id": "step_6",              // ← 又想新增同名 step_6
      ...
    }
  ]
}
```

### 1.3 自动纠正后的状态
```json
{
  "type": "PlanPatch",
  "remove_steps": [],              // ← 被清空（保留 add）
  "add_steps": [
    {
      "id": "step_6",              // ← 但现有计划中已有 step_6！冲突！
      ...
    }
  ]
}
```

---

## 2. 根本原因分析

### 2.1 自动纠正逻辑的缺陷

当前 `_auto_fix_patch_conflicts` 只处理了 **同一 patch 内部的冲突**：
- remove ∩ update → 保留 update
- remove ∩ add → 保留 add ← **这里出问题**
- update ∩ add → 保留 update

**问题**：保留 add 时，没有检查 add_steps 中的 step_id 是否与 **现有计划中的 step_id** 冲突。

### 2.2 LLM 的意图

LLM 实际想做的是"替换 step_6"：
1. 删除旧的 step_6
2. 新增一个修改后的 step_6（同名但内容不同）

**正确做法**：应该使用 `update_steps` 来修改现有步骤，而不是 remove + add。

---

## 3. 解决方案

### 3.1 方案 A：自动重命名冲突的 add_steps（推荐）

在自动纠正时，如果 add_steps 中的 step_id 在 remove_steps 中被移除，说明是"替换"意图，应该：
1. 转换为 `update_steps` 操作
2. 或者自动重命名为 `step_6_v2`

### 3.2 方案 B：增强错误提示

在 replan 提示词中明确告诉 LLM：
- 如果要"替换"步骤，请使用 `update_steps`
- `add_steps` 只用于新增**全新**的步骤

### 3.3 方案 C：组合方案（最佳）

1. **自动转换**：当检测到 "remove + add 同 id" 模式时，自动转换为 `update_steps`
2. **增强提示词**：告诉 LLM 正确用法

---

## 4. 实现计划

### 4.1 修改 `_auto_fix_patch_conflicts` 函数

```python
# 新增逻辑：当 remove ∩ add 时，将 add 转换为 update
rm_add_conflict = remove_ids & add_ids
if rm_add_conflict:
    # 将 add_steps 中的冲突项转移到 update_steps
    for add_step in obj.get("add_steps", []):
        if add_step.get("id") in rm_add_conflict:
            # 转换为 update
            update_entry = {"id": add_step["id"]}
            for key in ["description", "dependencies", "tools_expected"]:
                if key in add_step:
                    update_entry[key] = add_step[key]
            obj.setdefault("update_steps", []).append(update_entry)
    
    # 从 add_steps 中移除冲突项
    obj["add_steps"] = [s for s in obj.get("add_steps", []) if s.get("id") not in rm_add_conflict]
    # 从 remove_steps 中移除冲突项
    obj["remove_steps"] = [rid for rid in obj.get("remove_steps", []) if rid not in rm_add_conflict]
    warnings.append(f"自动转换：{list(rm_add_conflict)} 从 remove+add 转为 update（替换意图）")
```

### 4.2 修改 replan.j2 提示词

添加说明：
```
### 4. 替换步骤的正确方式
如果你想"替换"某个步骤（删除旧的，新增修改后的），请直接使用 `update_steps`：
```json
{
  "update_steps": [{"id": "step_6", "description": "新描述", "tools_expected": ["read_symbol"]}]
}
```
**不要用** `remove_steps` + `add_steps` 来替换同一个 step_id！
```

---

## 5. 代码变更清单

| 文件 | 变更类型 | 说明 | 状态 |
| :--- | :--- | :--- | :--- |
| `src/clude_code/orchestrator/planner.py` | 修改 | `_auto_fix_patch_conflicts` 增加 remove+add → update 转换 | ✅ 已完成 |
| `src/clude_code/prompts/user/stage/replan.j2` | 修改 | 增加"替换步骤的正确方式"说明 | ✅ 已完成 |

---

## 6. 验证结果

### 6.1 编译检查
```
python -m compileall -q src\clude_code\orchestrator\planner.py
# Exit code: 0 ✅
```

### 6.2 修复逻辑

**旧行为**：
```
LLM: remove_steps=["step_6"], add_steps=[{id: "step_6", ...}]
    ↓ 自动纠正
remove_steps=[], add_steps=[{id: "step_6", ...}]
    ↓ 应用 patch
错误：step_6 已存在于计划中！
```

**新行为**：
```
LLM: remove_steps=["step_6"], add_steps=[{id: "step_6", ...}]
    ↓ 自动转换
remove_steps=[], add_steps=[], update_steps=[{id: "step_6", ...}]
    ↓ 应用 patch
成功：step_6 被更新
```


