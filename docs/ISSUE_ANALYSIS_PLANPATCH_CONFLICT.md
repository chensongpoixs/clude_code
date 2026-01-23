# PlanPatch 解析冲突问题分析

> **分析日期**: 2026-01-23  
> **问题级别**: 🔴 严重（阻塞执行）

---

## 1. 问题现象

### 1.1 错误日志
```
✗ 重规划解析失败 patch_error=PlanPatch 内部冲突：同一步骤不能同时出现在 remove_steps/update_steps/add_steps 中。
rm∩update=['step_2'] rm∩add=[] update∩add=[]
```

### 1.2 LLM 返回的错误 JSON
```json
{
  "type": "PlanPatch",
  "title": "修正C++函数分析流程",
  "remove_steps": ["step_2"],      // ← step_2 要删除
  "update_steps": [
    {
      "id": "step_2",              // ← step_2 又要更新（冲突！）
      "description": "使用C++语法提取device.cpp函数定义",
      ...
    }
  ],
  "add_steps": [...]
}
```

### 1.3 上下文溢出
```
智能上下文裁剪: 6 → 5 条消息, 265759 tokens (811.0%)
```
**严重溢出！** 上下文使用率达到 811%，远超 100% 上限。

---

## 2. 根本原因分析

### 2.1 直接原因：LLM 误解了语义
LLM 想要"替换 step_2"，但理解为"先删除再更新"，而非使用 `update_steps` 单独操作。

**正确做法**：
- 如果要**修改**步骤内容 → 只用 `update_steps`
- 如果要**删除**步骤 → 只用 `remove_steps`
- 如果要**新增**步骤 → 只用 `add_steps`

### 2.2 间接原因：提示词不够强调约束
当前 `replan.j2` 提示词虽然列出了约束：
```
- **同一个 step_id 不能同时出现在 remove_steps / update_steps / add_steps** 中。
```
但在 811% 上下文溢出的情况下，这条约束可能被截断或被 LLM 忽略。

### 2.3 系统原因：上下文溢出导致行为不稳定
- `265759 tokens` 远超 `32768 max_tokens`
- 系统提示词/历史消息可能被截断
- LLM 看不到完整的约束说明

---

## 3. 错误传播链

```
[第一次 LLM 调用]
    ↓ 返回带有非法字段 (language, pattern) 的 update_steps
    ↓
[解析失败] → Pydantic ValidationError: Extra inputs not permitted
    ↓
[重试提示] → "PlanPatch 无法应用，需要你立刻纠正"
    ↓
[第二次 LLM 调用]
    ↓ 返回 step_2 同时在 remove_steps 和 update_steps
    ↓
[解析失败] → "PlanPatch 内部冲突"
    ↓
[回退到 FullPlan 解析] → 类型不匹配 (PlanPatch ≠ FullPlan)
    ↓
[最终失败] → ValueError: 无法从模型输出中解析 Plan JSON
```

---

## 4. 解决方案

### 4.1 短期修复：增强 PlanPatch 冲突自动纠正

**位置**: `src/clude_code/orchestrator/planner.py`

**策略**: 在解析 PlanPatch 时，如果检测到冲突，自动纠正而非直接报错。

```python
def _auto_fix_patch_conflicts(patch_data: dict) -> dict:
    """自动纠正 PlanPatch 冲突（优先保留 update_steps）"""
    remove_ids = set(patch_data.get("remove_steps", []))
    update_ids = set(s.get("id") for s in patch_data.get("update_steps", []))
    add_ids = set(s.get("id") for s in patch_data.get("add_steps", []))
    
    # 规则：如果同时在 remove 和 update，保留 update（修改意图强于删除）
    rm_update_conflict = remove_ids & update_ids
    if rm_update_conflict:
        patch_data["remove_steps"] = [
            rid for rid in patch_data.get("remove_steps", []) 
            if rid not in rm_update_conflict
        ]
        logger.warning(f"自动纠正冲突：从 remove_steps 中移除 {rm_update_conflict}")
    
    return patch_data
```

### 4.2 中期修复：强化 replan 提示词

**位置**: `src/clude_code/prompts/user/stage/replan.j2`

**改进**:
```jinja2
## ⚠️ 关键约束（必须遵守）

1. **唯一性规则**：同一个 step_id **绝对不能** 同时出现在 remove_steps / update_steps / add_steps 中。
   - ❌ 错误示例：`"remove_steps": ["step_2"], "update_steps": [{"id": "step_2", ...}]`
   - ✅ 正确示例（修改步骤）：`"update_steps": [{"id": "step_2", ...}]`
   - ✅ 正确示例（删除步骤）：`"remove_steps": ["step_2"]`

2. **修改 vs 删除**：
   - 想修改步骤内容？ → 用 `update_steps`
   - 想删除步骤？ → 用 `remove_steps`
   - **不要同时使用！**
```

### 4.3 长期修复：解决上下文溢出根因

**问题**: 上下文使用率 811% 表明系统提示词/历史消息远超 token 预算。

**已实施的保护措施**:
- `repo_map` 截断（20% token budget）
- System Prompt 总长度检查（50% token budget）

**需要进一步检查**:
1. 为什么 `_trim_history` 没有有效裁剪？
2. 是否有某条消息特别长（如工具返回结果）？
3. 考虑在 LLM 调用前做最终的 token 检查和强制截断。

---

## 5. 立即行动项

| 优先级 | 行动 | 文件 | 状态 |
| :--- | :--- | :--- | :--- |
| **P0** | 实现 `_auto_fix_patch_conflicts` | `planner.py` | ✅ 已完成 |
| **P0** | 在 LLM 调用前添加 token 硬上限检查 | `llm_io.py` | ✅ 已完成 |
| **P1** | 强化 replan.j2 提示词 | `replan.j2` | ✅ 已完成 |
| **P2** | 调查 811% 溢出的具体来源 + 错误消息去重 | `execution.py` | ✅ 已完成 |

### 5.1 已实施的 P0 修复

**1. `planner.py` - 自动纠正冲突**
```python
def _auto_fix_patch_conflicts(obj: dict) -> tuple[dict, list[str]]:
    # 规则：remove ∩ update → 保留 update
    # 规则：remove ∩ add → 保留 add
    # 规则：update ∩ add → 保留 update
```

**2. `llm_io.py` - 紧急截断**
```python
# 如果 token 使用率 > 95%，强制裁剪到只保留 system + 最近 3 条消息
if utilization > 0.95 and len(loop.messages) > 4:
    loop.messages = [system_msg] + recent_msgs[-3:]
```

---

## 6. 预防措施

### 6.1 Schema 层面
在 Pydantic 模型的 `model_validator` 中添加冲突检查，提供更友好的错误消息。

### 6.2 回退机制
当 PlanPatch 解析失败超过 2 次时，直接进入 ReAct fallback 模式，而非尝试解析 FullPlan。

### 6.3 Token 预算强制执行
在 `_llm_chat` 调用前，如果 token 使用率 > 95%，强制触发 emergency trim。


