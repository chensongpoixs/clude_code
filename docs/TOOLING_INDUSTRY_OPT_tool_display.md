## display（`src/clude_code/tooling/tools/display.py`）业界优化点

### 当前模块职责

- 让 agent 在执行过程中向用户输出**进度/说明/证据**；并在 `--live` 模式通过事件回调驱动 UI 刷新。

### 业界技术原理

- **Out-of-band progress channel**：把“进度与中间状态”从主对话里分离，避免污染上下文与误触发工具协议。
- **降级链路（graceful degradation）**：UI 回调失败不应影响主流程；最差也应写日志。
- **硬上限**：display 内容必须限制长度，避免“进度消息刷屏”挤爆上下文。

### 现状评估（本项目）

- 已实现：参数校验、level 规范化、长度截断、事件回调兜底、审计写入、控制台降级。

### 可优化点（建议优先级）

- **P1：标准化 display 的 payload 字段**
  - **原理**：UI/日志/回放依赖稳定字段。
  - **建议**：固定字段集：`content/level/title/truncated/trace_id`，并约束 evidence 为短列表。

- **P2：节流（throttle）与去重（dedupe）**
  - **原理**：长任务频繁 progress 会产生噪音。
  - **建议**：按 (trace_id, level) 做 250ms~1s 节流；相同 content 连续重复直接丢弃。


