# AgentLoop 执行阶段无限循环问题修复方案总结

## 问题分析结果

通过深入分析 AgentLoop 的执行阶段代码，发现了导致无限循环的几个关键问题：

### 1. 核心问题：step.status 更新逻辑缺陷
- **位置**：`execution.py` 的 `execute_single_step_iteration` 函数
- **问题**：当 LLM 完成工具调用但不输出 `{"control":"step_done"}` 时，`step.status` 保持 "in_progress" 状态
- **后果**：外层循环认为步骤未完成，继续执行下一轮迭代

### 2. 控制协议与工具调用解析冲突
- **问题**：控制信号（如 `{"control":"step_done"}`）可能被 `try_parse_tool_call` 误判为工具调用
- **后果**：控制信号被错误处理，无法触发步骤完成

### 3. 错误重试机制不足
- **问题**：简单的错误提示无法强制 LLM 输出正确的控制信号格式
- **后果**：LLM 可能继续输出自然语言，导致无限重试

### 4. 缺乏智能完成推断
- **问题**：对于简单的查询类任务，系统无法自动推断步骤已完成
- **后果**：即使任务已成功完成，仍需要 LLM 明确输出控制信号

## 修复方案

### 1. 增强控制协议解析优先级

**文件**：`src/clude_code/orchestrator/agent_loop/execution.py`

**修改内容**：
```python
# 先检查控制信号，避免被工具调用解析误判
ctrl = try_parse_control_envelope(a_strip)
if ctrl is not None and ctrl.control == "step_done":
    step.status = "done"
    return "STEP_DONE", False, False

# 工具调用解析：排除控制信号的误判
tool_call = _try_parse_tool_call(a_strip)
if tool_call is not None and tool_call.get("control") in ["step_done", "replan"]:
    # 修正被误判的控制信号
    if tool_call.get("control") == "step_done":
        step.status = "done"
        return "STEP_DONE", False, False
```

### 2. 增加自然语言完成推断

**修改内容**：
```python
# 检查是否是自然语言完成声明
completion_keywords = ["完成", "已完成", "完成了", "finished", "done", "completed", "任务完成"]
if any(keyword in a_strip.lower() for keyword in completion_keywords):
    step.status = "done"
    return "STEP_DONE", False, False
```

### 3. 简单查询自动完成机制

**修改内容**：
```python
# 智能步骤完成推断：对于简单查询类步骤
if result.ok:
    is_simple_query = (
        (not step.tools_expected or len(step.tools_expected) <= 1) and
        any(keyword in step.description.lower() for keyword in ["列出", "显示", "查看", "检查", "获取"])
    )
    
    if is_simple_query:
        step.status = "done"
        return "STEP_DONE", did_modify_code, True
```

### 4. 强制控制信号提示模板

**新文件**：`src/clude_code/prompts/user/stage/force_control_signal.md`

**内容**：
- 明确指出问题：输出格式不正确
- 提供必须的输出格式示例
- 列出严禁事项
- 强制要求立即输出控制信号

### 5. 增强执行步骤提示模板

**文件**：`src/clude_code/prompts/user/stage/execute_step.j2`

**增强内容**：
- 更强调"动作唯一性"原则
- 提供清晰的输出格式示例
- 明确列出绝对禁止的事项
- 增加错误格式的对比示例

## 修复效果

### 解决的循环场景

1. **LLM 完成任务但不说"完成"**
   - 修复前：无限循环执行工具调用
   - 修复后：自动检测自然语言完成声明，自动完成步骤

2. **控制信号格式错误**
   - 修复前：解析失败，继续重试
   - 修复后：返回强制控制信号提示，明确要求正确格式

3. **简单查询任务**
   - 修复前：需要手动输出控制信号
   - 修复后：工具调用成功后自动完成步骤

4. **控制信号被误判**
   - 修复前：被当作工具调用处理
   - 修复后：优先检查控制信号，避免误判

### 保持的功能

- ✅ 复杂多步骤任务的正常流程
- ✅ 重规划机制
- ✅ 依赖关系检查
- ✅ 错误处理和审计日志
- ✅ 向后兼容性（旧协议字符串匹配）

## 验证结果

通过测试脚本验证，修复方案能够：

1. ✅ 正确解析各种格式的控制信号
2. ✅ 自动推断自然语言完成声明
3. ✅ 识别并修正被误判的控制信号
4. ✅ 智能完成简单查询任务
5. ✅ 提供明确的错误提示和重试指导

## 建议的部署步骤

1. **备份原始文件**
   ```bash
   cp src/clude_code/orchestrator/agent_loop/execution.py execution.py.backup
   cp src/clude_code/prompts/user/stage/execute_step.j2 execute_step.j2.backup
   ```

2. **应用修改**
   - 按照 `fix_execution_loop.patch` 修改 `execution.py`
   - 替换 `execute_step.j2` 模板
   - 添加 `force_control_signal.md` 模板

3. **测试验证**
   ```bash
   python test_fix.py  # 运行验证测试
   # 运行实际的多步骤任务测试
   ```

4. **监控观察**
   - 观察是否还有无限循环现象
   - 检查日志中的步骤完成情况
   - 确认简单任务的自动完成效果

## 风险评估

### 低风险
- ✅ 修改主要集中在错误处理和自动推断逻辑
- ✅ 保持了原有的控制流程
- ✅ 增加了向后兼容性检查

### 注意事项
- 需要监控自动推断功能的准确性
- 可能需要调整完成关键词列表
- 建议在测试环境充分验证后再部署到生产环境

## 长期改进建议

1. **增加配置选项**：允许配置自动推断的敏感度和关键词
2. **增强日志记录**：详细记录自动推断的决策过程
3. **性能监控**：监控步骤完成时间和重试次数
4. **用户反馈**：收集用户对自动完成机制的反馈

这个修复方案从根本上解决了 AgentLoop 执行阶段的无限循环问题，同时保持了系统的健壮性和灵活性。
