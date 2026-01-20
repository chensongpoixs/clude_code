# ReAct 决策卡住问题分析与解决方案 (ReAct Decision Hang Analysis & Solution)

> **Issue (问题)**: ReAct 决策阶段一直显示 0% 完成，LLM 请求无响应  
> **Root Cause (根因)**: `max_tokens` 配置异常（409600）导致模型尝试生成过长输出  
> **Priority (优先级)**: P0 (Critical / 关键)

---

## 1. 问题分析 (Problem Analysis)

### 1.1 现象描述 (Symptoms)
从截图可见：
- **状态**: `EXECUTING`，操作 `LLM 请求`
- **进度**: `[ReAct 决策/直接回答]` 0% 完成
- **参数**: `max_tokens=409600`（异常大）
- **事件**: `step=10 llm_request_params` 后无后续响应

### 1.2 根因定位 (Root Cause)

#### 🔴 问题 1: `max_tokens` 配置错误
**位置**: `src/clude_code/config.py:14`
```python
max_tokens: int = Field(default=409600, ge=1)  # ❌ 错误：这是上下文窗口大小，不是输出限制
```

**影响**:
- `max_tokens` 在 OpenAI API 中表示**输出 token 限制**（通常 512-2048）
- 409600 会导致模型尝试生成极长输出，可能：
  - 触发服务端超时
  - 消耗大量计算资源
  - 导致请求卡死

#### 🟡 问题 2: 超时处理不够健壮
**位置**: `src/clude_code/llm/llama_cpp_http.py:123`
```python
with httpx.Client(timeout=self.timeout_s) as client:  # 默认 120 秒
    r = client.post(url, json=payload)
```

**影响**:
- 虽然代码有 `TimeoutException` 处理，但异常可能未正确传播到 UI
- UI 层面缺少超时提示和重试机制

#### 🟡 问题 3: 错误反馈链路不完整
**位置**: `src/clude_code/orchestrator/agent_loop/react.py:37`
```python
assistant = _llm_chat("react_fallback", None)  # 如果这里抛异常，UI 可能收不到事件
```

**影响**:
- LLM 请求失败时，`_ev` 事件流可能中断
- UI 无法感知到错误，一直显示"等待中"

---

## 2. 解决方案 (Solutions)

### 2.0 业界做法对齐（Industry Playbook / 业界处置手册）

业界（Claude Code/Aider/Cursor/OpenCode）在处理“LLM 请求卡住/无限等待”时，通常遵循同一套工程护栏（Guardrails/护栏）：

1. **Hard Limits（硬限制）**：
   - 输出 token 上限（`max_tokens`）必须合理（典型 512~2048）。
   - 请求超时（`timeout_s`）必须可配置（典型 30~120s），并在 UI 明确展示“已超时/可重试”。
2. **Circuit Breaker（熔断器）**：
   - 同一阶段连续超时/失败超过阈值，直接中止并提示“缩小问题/检查模型服务”。
3. **User-visible Failure（用户可见失败）**：
   - 失败必须成为 UI 事件（例如 `llm_error`），而不是静默导致“0% 等待中”。
4. **Retry Policy（重试策略）**：
   - 只对明确幂等的 LLM 请求做有限次数重试（例如 1~2 次），并做退避（Backoff/退避）。
5. **Observability（可观测性）**：
   - 记录请求开始时间、耗时、超时原因、关键参数（model/max_tokens/messages_count），写入 audit/trace。

### 2.1 P0: 修复 `max_tokens` 配置（立即修复）

**修改文件**: `src/clude_code/config.py`

```python
# Before (修改前)
max_tokens: int = Field(default=409600, ge=1)  # ❌ 错误

# After (修改后)
max_tokens: int = Field(default=1024, ge=1, le=8192, description="LLM 输出 token 限制（非上下文窗口大小）")
```

**说明**:
- 1024 是合理的默认值（适合大多数任务）
- `le=8192` 防止用户配置过大值
- 添加描述明确这是"输出限制"，不是上下文窗口

### 2.2 P0: 增强超时与错误处理（立即修复）

**修改文件**: `src/clude_code/orchestrator/agent_loop/react.py`

```python
# 在 execute_react_fallback_loop 中增加异常捕获
try:
    assistant = _llm_chat("react_fallback", None)
except RuntimeError as e:
    error_msg = str(e)
    if "timeout" in error_msg.lower():
        _ev("llm_error", {"error": "timeout", "message": f"LLM 请求超时（{loop.llm.timeout_s}秒）"})
        loop.logger.error(f"[red]LLM 请求超时: {error_msg}[/red]")
        return AgentTurn(
            assistant_text=f"LLM 请求超时（{loop.llm.timeout_s}秒）。请检查模型服务是否正常运行，或尝试降低 max_tokens。",
            tool_used=False,
            trace_id=trace_id,
            events=events,
        )
    else:
        _ev("llm_error", {"error": "request_failed", "message": error_msg})
        loop.logger.error(f"[red]LLM 请求失败: {error_msg}[/red]")
        return AgentTurn(
            assistant_text=f"LLM 请求失败: {error_msg}",
            tool_used=False,
            trace_id=trace_id,
            events=events,
        )
```

### 2.3 P1: UI 层面超时提示（后续优化）

**修改文件**: `src/clude_code/plugins/ui/opencode_tui.py`

在 `_refresh_ops` 中检测 LLM 请求是否超时：
```python
# 如果 LLM 请求超过 timeout_s * 1.5，显示超时警告
if elapsed_ms > (self._agent.cfg.llm.timeout_s * 1500):
    # 显示超时警告
    self._push_chat_log("⚠️ LLM 请求可能已超时，请检查模型服务", style="yellow")
```

---

## 3. 验证步骤 (Verification Steps)

1. **修复配置后重启**:
   ```bash
   # 修改 config.py 后，重启 clude chat
   clude chat --live --live-ui opencode
   ```

2. **验证 `max_tokens`**:
   - 查看 TUI 中的 `llm_request_params` 事件
   - 确认 `max_tokens` 为 1024（或合理值）

3. **测试超时处理**:
   - 故意停止模型服务
   - 确认 UI 显示错误提示，而非一直等待

---

## 4. 预防措施 (Prevention)

1. **配置校验**: 在 `LLMConfig` 初始化时校验 `max_tokens <= 8192`
2. **文档更新**: 在 `docs/18-troubleshooting-faq.md` 中补充此问题
3. **监控告警**: 在 UI 中显示 LLM 请求耗时，超过阈值时提示

4. **熔断策略（Circuit Breaker / 熔断）**：
   - 连续 N 次 LLM 超时（例如 N=2）后，直接停止本轮并输出“服务异常/建议降低 max_tokens/检查 base_url”。

---

## 5. 相关文件 (Related Files)

- **配置**: `src/clude_code/config.py`
- **LLM 客户端**: `src/clude_code/llm/llama_cpp_http.py`
- **ReAct 循环**: `src/clude_code/orchestrator/agent_loop/react.py`
- **UI（界面）**: `src/clude_code/plugins/ui/opencode_tui.py`

