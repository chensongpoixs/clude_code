# AgentLoop 执行阶段无限循环问题分析报告

## 问题概述
程序在执行多步骤任务时（如"列出当前目录的前3个文件"）陷入了循环，反复执行相同的步骤1，无法进入步骤2。

## 核心问题分析

### 1. 关键逻辑缺陷：step.status 未在正确时机更新

在 `execution.py` 的 `execute_single_step_iteration` 函数中：

```python
# 第131-141行：控制信号处理
if ctrl is not None and ctrl.control == "step_done":
    loop.messages.append(ChatMessage(role="assistant", content=assistant))
    loop._trim_history(max_messages=30)
    step.status = "done"  # ✓ 正确设置状态
    return "STEP_DONE", False, False

# 第183-214行：工具调用处理
tool_call = _try_parse_tool_call(assistant)
if tool_call is not None:
    # ... 处理工具调用
    return None, did_modify_code, True  # ✗ 没有更新 step.status
```

**问题**：当工具调用完成但 LLM 不输出 `{"control":"step_done"}` 时，`step.status` 保持 "in_progress" 状态，导致外层循环认为步骤未完成。

### 2. 外层循环逻辑问题

在 `execute_plan_steps` 函数中（第450-473行）：

```python
for iteration in range(loop.cfg.orchestrator.max_step_tool_calls):
    control_signal, iter_did_modify, iter_did_use_tool = execute_single_step_iteration(...)
    
    if control_signal in ("STEP_DONE", "REPLAN"):
        break  # 只有收到控制信号才跳出循环

# 第475-477行：循环结束后的状态检查
if step.status == "done":
    step_cursor += 1
    continue
```

**问题**：如果 LLM 从不输出 `step_done`，`control_signal` 永远是 `None`，循环会执行完整的 `max_step_tool_calls` 次数，但 `step.status` 从未变为 "done"。

### 3. 错误重试机制的缺陷

在 `execute_single_step_iteration` 第184-197行：

```python
if tool_call is None:
    loop.messages.append(ChatMessage(role="assistant", content=assistant))
    error_prompt = read_prompt("user/stage/invalid_step_output_retry.md").strip()
    # ... 检查是否已有错误提示
    loop.messages.append(ChatMessage(role="user", content=error_prompt))
    return None, False, False  # 继续下一轮迭代
```

**问题**：错误重试只是简单的消息追加，没有强制要求 LLM 输出控制信号。

### 4. 控制协议解析与工具调用解析的冲突

调试结果显示，当 LLM 输出 `{"control":"step_done"}` 时，`try_parse_control_envelope` 能正确解析，但如果格式稍有偏差（如包含额外文本），就会被 `try_parse_tool_call` 误识别为工具调用。

## 无限循环触发场景

### 场景1：LLM 完成任务但不说"完成"
```
LLM: {"tool": "list_dir", "args": {"path": ".", "max_items": 3}}
系统: [执行工具，返回结果]
LLM: 我已经成功列出了目录内容。
系统: [无法识别为控制信号或工具调用，返回错误提示]
LLM: {"tool": "list_dir", "args": {"path": ".", "max_items": 3}}  # 重复调用
系统: [再次执行工具]
```

### 场景2：控制信号格式不正确
```
LLM: {control: "step_done"}  # 缺少引号
系统: [控制协议解析失败，工具调用解析也失败]
```

### 场景3：LLM 忽略提示继续输出自然语言
```
LLM: 任务已完成。
系统: [返回错误提示]
LLM: 我明白了，让我继续。  # 仍然不输出控制信号
```

## 修复建议

### 1. 强制执行规则增强
在 `execute_step.j2` 提示模板中：
- 增加更明确的"状态闭环"要求
- 提供 JSON 输出示例
- 强调"严禁任何其他输出"

### 2. 智能状态推断
在 `execute_single_step_iteration` 中：
```python
# 在工具调用完成后，自动推断是否应该完成步骤
if tool_call is not None and result.ok:
    # 检查是否是分析类步骤或简单的查询类步骤
    if step.is_simple_query() or step.is_analysis_step():
        step.status = "done"
        return "STEP_DONE", False, True
```

### 3. 改进错误重试机制
```python
if tool_call is None and ctrl is None:
    # 检查是否是简单的完成声明
    if any(keyword in assistant.lower() for keyword in ["完成", "完成", "finished", "done"]):
        step.status = "done"
        return "STEP_DONE", False, False
    
    # 强制要求输出控制信号
    error_prompt = render_prompt("user/stage/force_control_signal.md", 
                                last_output=assistant[:200])
    loop.messages.append(ChatMessage(role="user", content=error_prompt))
    return None, False, False
```

### 4. 控制协议解析优先级调整
在 `execute_single_step_iteration` 中：
```python
# 先尝试控制协议解析
ctrl = try_parse_control_envelope(a_strip)
if ctrl is not None:
    # 处理控制信号
    pass

# 再尝试工具调用解析，但要排除控制信号误判
tool_call = _try_parse_tool_call(a_strip)
if tool_call is not None and tool_call.get("control") not in ["step_done", "replan"]:
    # 处理工具调用
    pass
```

### 5. 增加超时和强制完成机制
```python
# 在外层循环中增加强制完成检查
if iteration >= loop.cfg.orchestrator.max_step_tool_calls - 1:
    if step.status == "in_progress":
        # 检查是否有成功的工具调用
        if iter_did_use_tool and not iter_failed:
            loop.logger.warning(f"强制完成步骤 {step.id}（达到最大迭代次数）")
            step.status = "done"
            break
```

## 建议的修改文件

1. `src/clude_code/prompts/user/stage/execute_step.j2` - 增强提示
2. `src/clude_code/orchestrator/agent_loop/execution.py` - 修复逻辑
3. `src/clude_code/prompts/user/stage/force_control_signal.md` - 新增强制提示
4. `src/clude_code/orchestrator/agent_loop/parsing.py` - 改进解析逻辑

## 测试验证

建议添加以下测试用例：
1. LLM 完成任务但不输出控制信号的场景
2. 控制信号格式错误的场景  
3. 多轮工具调用后自动推断完成的场景
4. 达到最大迭代次数的强制完成场景

这些修改将有效解决无限循环问题，同时保持系统的健壮性和灵活性。
