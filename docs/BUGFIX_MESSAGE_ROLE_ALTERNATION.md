# BugFix: 消息角色交替问题分析与修复

## 问题现象

```
llama.cpp OpenAI-compatible request failed: status=500
body={"error":{"code":500,"message":"Conversation roles must alternate user/assistant/user/assistant/..."
```

## 问题分析

### 1. 错误的消息序列

从日志可以看到发送给 LLM 的 messages 结构：

```python
[
  {'role': 'system', 'content': '# 核心元规则...'},
  {'role': 'assistant', 'content': '{"type": "FullPlan"...'},  # ❌ system 后直接是 assistant
  {'role': 'user', 'content': '【当前执行步骤】：step_1...'},
  {'role': 'assistant', 'content': '{"tool": "get_weather"...'},
  {'role': 'user', 'content': '{"query": {"city": "Beijing"...'}
]
```

### 2. 根因

Gemma 模型的 chat template 有严格要求：
1. 第一条消息可以是 `system`（可选）
2. **`system` 之后的第一条消息必须是 `user`**
3. 之后必须严格交替：`user` → `assistant` → `user` → `assistant` ...

当前的 `normalize_messages_for_llama` 函数只确保相邻消息角色交替，但没有确保 **system 后第一条必须是 user**。

### 3. 问题来源

在规划阶段：
1. 添加 user 消息（规划请求）
2. LLM 返回 assistant 消息（FullPlan）
3. 进入执行阶段
4. 执行阶段添加新的 user 消息（execute_step prompt）
5. **智能裁剪时，可能将早期的 user 消息（规划请求）裁剪掉**
6. 导致 system 后直接是 assistant

## 解决方案

### 方案 A：在 normalize 中插入占位 user 消息（推荐）

如果 system 后的第一条消息是 assistant，插入一个占位 user 消息：

```python
# 确保 system 后第一条是 user
if len(normalized) >= 2:
    first_non_system = normalized[1] if normalized[0].role == "system" else normalized[0]
    if first_non_system.role == "assistant":
        # 插入占位 user 消息
        placeholder = ChatMessage(role="user", content="请继续执行任务。")
        insert_idx = 1 if normalized[0].role == "system" else 0
        normalized.insert(insert_idx, placeholder)
```

### 方案 B：裁剪时保护配对完整性

在 `_trim_history` 中，确保裁剪时保留 user-assistant 配对的完整性。

### 选择方案 A

- 更简单，在最终出口处统一处理
- 不影响其他逻辑
- 兼容所有模型的 chat template 要求

## 实现

修改 `src/clude_code/orchestrator/agent_loop/llm_io.py` 中的 `normalize_messages_for_llama` 函数。

## 验证

```bash
python -c "
from clude_code.llm.llama_cpp_http import ChatMessage
from clude_code.orchestrator.agent_loop.llm_io import normalize_messages_for_llama

class MockLoop:
    def __init__(self):
        self.messages = [
            ChatMessage(role='system', content='system prompt'),
            ChatMessage(role='assistant', content='plan json'),
            ChatMessage(role='user', content='execute step'),
        ]
    def _trim_history(self, max_messages):
        pass

loop = MockLoop()
normalize_messages_for_llama(loop, 'test')
for m in loop.messages:
    print(f'{m.role}: {m.content[:30]}...')
"
```

期望输出：
```
system: system prompt...
user: 请继续执行任务。...
assistant: plan json...
user: execute step...
```

## 状态

- [x] 问题分析
- [x] 代码实现
- [x] 编译检查通过
- [x] Lint 检查通过

## 修改文件

- `src/clude_code/orchestrator/agent_loop/llm_io.py`
  - 在 `normalize_messages_for_llama` 函数中添加第三遍处理
  - 确保 system 后第一条消息是 user
  - 如果不是，插入占位消息 "请继续执行任务。"

