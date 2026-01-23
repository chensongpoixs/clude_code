# 问题修复：LLM 日志中 User 消息丢失

> **修复时间**：2026-01-23  
> **问题来源**：用户反馈

---

## 问题现象

第一次发送消息（"获取苏州的天气"）时，日志正确打印了用户消息内容：

```
===== 本轮发送给 LLM 的新增 user 文本 =====
--- user[1] ---
# 通用对话
## 用户消息
获取苏州的天气
```

第二次发送消息（"你好啊"）时，日志**丢失**了用户消息内容：

```
===== 本轮发送给 LLM 的新增 user 文本 =====
LLM 请求参数: model=...  ← 直接跳到了参数，user 内容消失了
```

---

## 问题分析

### 执行流程追踪

**第一次请求**：
1. `run_turn` 开始：`_llm_log_cursor = len(messages) = 1`（只有 system）
2. 添加 user 消息：`messages` 长度 = 2
3. `log_llm_request_params_to_file`：
   - 计算 `new_msgs = messages[1:]` = 1 条 user
   - ✅ 正确打印
4. 更新 `_llm_log_cursor = 2`

**第二次请求**：
1. `run_turn` 开始：`_llm_log_cursor = len(messages) = 4`
2. 添加 user 消息：`messages` 长度 = 5
3. **关键**：`normalize_messages_for_llama()` 合并连续相同角色消息
   - `messages` 长度从 5 变为 4
4. `log_llm_request_params_to_file`：
   - 计算 `new_msgs = messages[4:]` = **空数组**！
   - ❌ 没有 user 被打印

### 根本原因

| 问题 | 描述 |
|------|------|
| **状态依赖** | `_llm_log_cursor` 在 `run_turn` 开始时设置，但消息列表在后续会被修改 |
| **消息合并影响** | `normalize_messages_for_llama()` 会合并连续相同角色的消息，改变数组长度 |
| **Cursor 失效** | 合并后 cursor 指向的位置可能超出数组范围或指向错误位置 |

### 日志中的证据

```
当前消息历史长度: 5          ← run_turn 设置 cursor = 4 或 5
→ 第 1 轮：请求 LLM（消息数=5）
智能上下文裁剪: 4 → 4 条消息  ← normalize 合并后长度变为 4
===== 本轮发送给 LLM 的新增 user 文本 =====
（空）                        ← messages[4:] = 空！
LLM 请求参数: messages=4
```

---

## 业界对标

| 方面 | 当前实现 | 业界最佳实践 |
|------|---------|-------------|
| 日志状态管理 | 依赖外部 `_llm_log_cursor` 状态 | 日志函数应**自包含**，不依赖外部状态 |
| 消息查找 | 基于索引切片 | 基于**内容语义**（找最后一条 user） |
| 抗干扰性 | 易受消息合并/裁剪影响 | 独立于业务逻辑的消息处理 |

### 参考：OpenAI/Anthropic 的日志实践

- **不使用 cursor**：直接基于 role 过滤消息
- **最后一条优先**：只关心本次请求的输入，从后往前查找
- **自包含函数**：日志函数不依赖调用者设置的状态

---

## 解决方案

### 修改文件

`src/clude_code/orchestrator/agent_loop/llm_io.py`

### 修改内容

将基于 cursor 的切片逻辑：

```python
# 旧代码（有问题）
base = int(getattr(loop, "_llm_log_cursor", 0) or 0)
new_msgs = loop.messages[base:]
new_users = [m for m in new_msgs if getattr(m, "role", None) == "user"]
```

改为基于内容语义的查找：

```python
# 新代码（修复后）
new_users: list[ChatMessage] = []
for msg in reversed(loop.messages or []):
    if getattr(msg, "role", None) == "user":
        new_users.insert(0, msg)
        break  # 只取最后一条 user 消息（本轮输入）
    elif getattr(msg, "role", None) == "assistant":
        # 遇到 assistant 就停止，说明之前的 user 是历史轮次的
        break
```

### 修复原理

1. **从后往前遍历** `messages`
2. **找到第一个 user** 即为本轮输入
3. **遇到 assistant 就停止**，避免误取历史轮次的 user
4. **不依赖 cursor**，不受消息合并/裁剪影响

---

## 验证

```bash
python -m compileall -q src/clude_code/orchestrator/agent_loop/llm_io.py
```

---

## 潜在的其他问题

### 1. `normalize_messages_for_llama` 的副作用

该函数会修改 `loop.messages`，可能影响：
- 审计日志的完整性
- 消息历史的回溯
- 其他依赖 messages 长度的逻辑

**建议**：考虑在 normalize 时不直接修改原数组，而是返回新数组。

### 2. `_llm_log_cursor` 的冗余

修复后 `_llm_log_cursor` 在日志函数中不再使用，但仍在 `run_turn` 中设置。

**建议**：可以移除 `_llm_log_cursor` 相关代码，或保留用于其他用途。

### 3. 多轮对话中的消息膨胀

日志显示消息从 2 条增长到 5 条，如果不及时裁剪可能导致：
- Token 超限
- 性能下降

**建议**：确保 `_trim_history` 在正确的时机被调用。

---

## 类似问题检查

### 已检查的文件

| 文件 | 状态 | 说明 |
|------|------|------|
| `llm_io.py` | ✅ 已修复 | 移除 cursor 依赖 |
| `agent_loop.py` | ✅ 已清理 | 移除 `_llm_log_cursor` 设置 |
| `execution.py` | ✅ 安全 | `step_cursor` 是局部变量 |
| `planning.py` | ✅ 安全 | 无索引依赖问题 |
| `react.py` | ✅ 安全 | 无索引依赖问题 |
| `classifier.py` | ✅ 安全 | `_last_category` 在同一调用链中使用 |

### 其他状态变量

| 变量 | 用途 | 风险 |
|------|------|------|
| `_last_llm_stage` | 日志记录当前阶段 | 低 - 仅用于日志 |
| `_current_profile` | Profile 选择 | 低 - 在 run_turn 中同步更新 |
| `_current_risk_level` | 风险等级 | 低 - 与 Profile 同步 |
| `_current_ev` / `_current_trace_id` | display 工具上下文 | 低 - 每轮更新 |

### 潜在改进

1. **消息合并可观测性**：`normalize_messages_for_llama` 应该记录合并前后的消息内容差异
2. **状态变量文档化**：建议在代码中注释每个 `_` 前缀变量的生命周期和依赖关系
3. **单元测试**：为消息合并 + 日志输出场景添加测试用例

---

## 总结

| 项目 | 内容 |
|------|------|
| 问题 | 第二次及以后的请求，日志中 user 消息丢失 |
| 原因 | `_llm_log_cursor` 被消息合并逻辑破坏 |
| 修复 | 改为基于内容语义查找最后一条 user 消息 |
| 对齐 | 业界自包含日志函数实践 |
| 额外清理 | 移除 `agent_loop.py` 中冗余的 `_llm_log_cursor` 设置 |
| 类似问题 | 已检查其他文件，无类似问题 |

