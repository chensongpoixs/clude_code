# P1-2: TodoManager 协议强化实现

> **状态**: 🔄 进行中  
> **开始时间**: 2026-01-23

---

## 1. 问题分析

### 1.1 当前行为
```python
# todo_manager.py L164-167
if content.startswith("update:"):  # ← "暗号协议"
    parts = content.split(":", 2)
    if len(parts) == 3:
        todo_id = parts[1].strip()
        new_content = parts[2].strip()
```

### 1.2 问题
- 使用 `"update:"` 字符串前缀是"暗号协议"
- 模型容易写错格式（如 `"Update:"` / `"update: "` / 忘记第二个冒号）
- 无法利用 JSON Schema 进行参数校验
- 违背"显式优于隐式"原则

### 1.3 业界对标
| 系统 | 策略 |
| :--- | :--- |
| REST API | 使用不同的 HTTP 方法（POST vs PUT）或资源 ID 参数 |
| GraphQL | 显式的 `mutation createTodo` vs `mutation updateTodo` |
| Claude Code | 工具参数中显式的 `id` 字段 |

---

## 2. 设计方案

### 2.1 技术路线
1. 在 `todowrite` 函数中添加显式的 `todo_id: str | None` 参数
2. 逻辑：
   - 如果 `todo_id` 非空 → 更新已有任务
   - 如果 `todo_id` 为空 → 创建新任务
3. 移除 `"update:"` 前缀解析逻辑
4. 更新 `tool_dispatch.py` 中的 JSON Schema

### 2.2 新 API 签名
```python
def todowrite(
    content: str,
    priority: str = "medium",
    status: str = "pending",
    todo_id: str | None = None,  # ← 新增：显式 ID
) -> ToolResult:
```

### 2.3 JSON Schema 更新
```json
{
  "type": "object",
  "properties": {
    "content": {"type": "string", "description": "任务内容"},
    "priority": {"type": "string", "enum": ["high", "medium", "low"]},
    "status": {"type": "string", "enum": ["pending", "in_progress", "completed", "cancelled"]},
    "todo_id": {"type": "string", "description": "任务ID（传入则更新，不传则创建）"}
  },
  "required": ["content"]
}
```

---

## 3. 实现步骤

- [x] 3.1 修改 `todowrite` 函数签名，添加 `todo_id` 参数 ✅
- [x] 3.2 修改逻辑：根据 `todo_id` 是否存在决定创建/更新 ✅
- [x] 3.3 移除 `"update:"` 前缀解析逻辑 ✅
- [x] 3.4 更新 `tool_dispatch.py` 中的 JSON Schema ✅
- [x] 3.5 更新 `local_tools.py` 中的方法签名 ✅
- [x] 3.6 编译检查 ✅ 通过
- [x] 3.7 验证汇报 ✅ 完成

---

## 5. 验证结果

### 5.1 编译检查
```
python -m compileall -q todo_manager.py local_tools.py tool_dispatch.py
# Exit code: 0 ✅
```

### 5.2 核心变更摘要

**`todo_manager.py`**:
- 新增 `todo_id: Optional[str] = None` 参数
- 移除 `"update:"` 前缀解析逻辑
- 根据 `todo_id` 是否存在决定创建/更新
- 增加详细日志

**`tool_dispatch.py`**:
- `_h_todowrite` 传递 `todo_id` 参数
- `_spec_todowrite` 添加 `todo_id` 到 JSON Schema

**`local_tools.py`**:
- `todowrite` 方法签名同步更新

### 5.3 使用示例
```python
# 创建新任务
{"tool": "todowrite", "args": {"content": "修复 bug", "priority": "high"}}

# 更新已有任务
{"tool": "todowrite", "args": {"todo_id": "abc-123", "content": "修复 bug (已验证)", "status": "completed"}}
```

### 5.4 预期收益
- 消除"暗号协议"，模型不会再写错格式
- JSON Schema 强约束确保参数有效性
- 更清晰的 API 语义

---

## 4. 代码变更清单

| 文件 | 变更类型 | 说明 |
| :--- | :--- | :--- |
| `src/clude_code/tooling/tools/todo_manager.py` | 修改 | 添加 `todo_id` 参数，移除暗号协议 |
| `src/clude_code/orchestrator/agent_loop/tool_dispatch.py` | 修改 | 更新 JSON Schema |


