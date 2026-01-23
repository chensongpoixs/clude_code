# P0-2: Question 工具阻塞协议实现

> **状态**: 🔄 进行中  
> **开始时间**: 2026-01-23

---

## 1. 问题分析

### 1.1 当前行为
```python
# question.py - 返回 pending 状态，但不会真正阻塞
result_data = {
    "type": "question",
    "data": question_data,
    "status": "pending"  # ← 这只是数据，没有控制流语义
}
return ToolResult(ok=True, payload=result_data)
```

### 1.2 问题
- `question` 工具返回后，Agent 继续执行下一步。
- 由于没有收到用户答案，Agent 会基于错误假设继续推理。
- 可能导致"自问自答"或忽略用户输入的循环。

### 1.3 业界对标
| 系统 | 策略 |
| :--- | :--- |
| Claude Code | `question` 返回后进入 `WAITING_INPUT` 状态，中断当前 turn |
| Cursor | Human-in-the-loop (HITL)：模型发起请求 → UI 收集输入 → 下一轮继续 |
| LangChain | `HumanInputTool` 使用回调机制通知 Executor 暂停 |

---

## 2. 设计方案

### 2.1 核心思路
1. 在 `AgentLoop` 中维护 `_waiting_user_input: bool` 状态标志。
2. 在 `_run_tool_lifecycle` 执行完成后检测结果：
   - 如果 `payload.get("type") == "question"` 且 `payload.get("status") == "pending"`
   - 设置 `self._waiting_user_input = True`
   - 记录待回答的问题数据
3. 在 `run_turn` 的主循环中检测 `_waiting_user_input`：
   - 如果为 True，提前返回一个特殊结果，通知调用者需要用户输入
4. 调用者（CLI/UI）收到后，收集用户输入并调用 `agent.answer_question(answer)`
5. `answer_question` 方法将答案注入 messages 并清除 `_waiting_user_input` 标志

### 2.2 数据流
```
[Agent] question("选项？")
    ↓
[tool_lifecycle] 执行 → payload = {type: "question", status: "pending"}
    ↓
[agent_loop] 检测到 question pending → 设置 _waiting_user_input = True
    ↓
[run_turn] 检测到 _waiting_user_input → return TurnResult(needs_input=True, question_data=...)
    ↓
[CLI/UI] 显示问题 → 收集用户输入
    ↓
[CLI/UI] agent.answer_question("用户的回答")
    ↓
[agent_loop] 注入答案到 messages → 清除 _waiting_user_input → 继续执行
```

### 2.3 API 设计
```python
class AgentLoop:
    # 新增状态
    _waiting_user_input: bool = False
    _pending_question: dict[str, Any] | None = None
    
    # 新增方法
    def answer_question(self, answer: str | list[str]) -> None:
        """提供 question 工具的答案，恢复执行。"""
        ...
    
    def is_waiting_input(self) -> bool:
        """检查是否正在等待用户输入。"""
        return self._waiting_user_input
```

---

## 3. 实现步骤

- [x] 3.1 在 `AgentLoop.__init__` 中添加状态字段 ✅
- [x] 3.2 在 `_run_tool_lifecycle` 后添加 question 检测逻辑 ✅
- [x] 3.3 实现 `answer_question` 方法 ✅
- [x] 3.4 实现 `is_waiting_input` 和 `get_pending_question` 方法 ✅
- [x] 3.5 编译检查 ✅ 通过
- [x] 3.6 验证汇报 ✅ 完成

---

## 5. 验证结果

### 5.1 编译检查
```
python -m compileall -q agent_loop.py tool_lifecycle.py
# Exit code: 0 ✅
```

### 5.2 核心变更摘要

**新增状态字段**:
- `_waiting_user_input: bool` - 阻塞标志
- `_pending_question: dict | None` - 待回答问题数据

**`_run_tool_lifecycle` 增强**:
- 检测 `payload.type == "question"` 且 `payload.status == "pending"`
- 自动设置阻塞标志并触发 `question_pending` 事件

**新增 API**:
- `is_waiting_input()` - 检查是否等待输入
- `get_pending_question()` - 获取问题数据
- `answer_question(answer)` - 提供答案并恢复执行

### 5.3 使用示例
```python
# CLI/UI 侧
result = agent.run_turn(user_input, confirm=..., on_event=handle_event)

if agent.is_waiting_input():
    question = agent.get_pending_question()
    # 显示问题并收集用户输入
    user_answer = prompt_user(question)
    agent.answer_question(user_answer)
    # 继续执行
    result = agent.run_turn("", confirm=..., on_event=handle_event)
```

### 5.4 预期收益
- 消除 Question 工具的"假死"现象
- 实现完整的 Human-in-the-loop 协议

---

## 4. 代码变更清单

| 文件 | 变更类型 | 说明 |
| :--- | :--- | :--- |
| `src/clude_code/orchestrator/agent_loop/agent_loop.py` | 增强 | 添加状态字段和 `answer_question` 方法 |
| `src/clude_code/orchestrator/agent_loop/tool_lifecycle.py` | 增强 | 添加 question pending 检测 |


