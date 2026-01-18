# 12 | 可观测性（可实现规格）(Observability Spec)

> **Status (状态)**: Stable Spec (稳定规格，已落地)  
> **Audience (读者)**: Maintainers / DevOps (维护者/运维人员)  
> **Goal (目标)**: 让系统“可调试 (Debuggable)、可评估 (Evaluable)、可审计 (Auditable)”，并能定位失败原因与性能瓶颈。

---

## 1. 审计日志 (Audit Log)

> **当前实现 (Current Implementation)**: `~/.clude/audit.jsonl`

### 1.1 结构化日志 (Structured Logging)
所有核心事件（Event）都以 JSONL 格式写入，确保机器可读。

关键字段：
- `trace_id` (UUID): 贯穿一次任务的唯一标识。
- `timestamp`: 时间戳。
- `event`: 事件类型 (`tool_call`, `llm_request`, `error`)。
- `level`: `INFO`, `WARN`, `ERROR`。
- `payload`: 事件详情（已脱敏）。

### 1.2 Trace ID 治理
- **生成**: 在 `AgentLoop.run_turn` 开始时生成 `uuid4`。
- **传递**: 传递给所有工具调用和子模块。
- **展示**: 在 TUI 界面和错误报告中显示，方便用户反馈。

---

## 2. 实时状态监控 (Live Monitoring)

### 2.1 TUI 状态面板
- **Token Usage**: 实时显示 Context/Output Token 使用量。
- **TPS**: 推理速度 (Tokens Per Second)。
- **Step**: 当前执行步骤与总步数。

### 2.2 成本估算
- **SessionUsage**: 统计本轮会话的 Token 总消耗与预估成本。
- **`display`**: 通过 `display` 工具向用户展示耗时任务的进度。

---

## 3. 回放与复现 (Replay & Reproduction)

### 3.1 场景
- **Bug 报告**: 用户提交 `trace_id`，开发者通过 `audit.jsonl` 复现上下文。
- **回归测试**: 将历史成功的 `audit.jsonl` 转化为测试用例。

---

## 4. 业界对比 (Industry Comparison)

| 维度 | Clude Code | Aider | Claude Code | 评价 |
| :--- | :--- | :--- | :--- | :--- |
| **日志格式** | ✅ JSONL (Structured) | ❌ 文本日志 | ✅ JSONL | 业界标准 |
| **Trace ID** | ✅ UUID | ❌ 无显式 ID | ✅ 有 | **领先** |
| **Token 监控** | ✅ 实时 TPS/Usage | ✅ 每次请求后 | ✅ 实时 | 持平 |
| **成本归因** | ⏳ 待完善 (Session级) | ✅ 累积统计 | ✅ 详细归因 | 需改进 |

---

## 5. 相关文档 (See Also)

- **工具协议 (Tool Protocol)**: [`docs/02-tool-protocol.md`](./02-tool-protocol.md)
- **Agent 决策链路审计 (Decision Audit)**: [`docs/17-agent-decision-audit.md`](./17-agent-decision-audit.md)
