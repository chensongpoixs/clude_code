# 12｜可观测性（Logging / Metrics / Tracing / Replay）

目标：让系统“可调试、可评估、可审计”，并能定位失败原因与性能瓶颈。

## 1. 日志（Logging）

### 1.1 日志类型
- **交互日志**：用户输入、模型输出（可选脱敏）、会话摘要
- **工具日志**：ToolCallRequest/Result（结构化）
- **系统日志**：异常、超时、资源占用

### 1.2 结构化字段（建议统一）
- `timestamp`
- `trace_id`（贯穿一次任务）
- `session_id`
- `plan_id`
- `tool_call_id`
- `level`
- `event`
- `duration_ms`

### 1.3 脱敏与采样
- 默认脱敏：token/key/password
- 对大输出采用采样/截断，但必须保留“错误尾部”

## 2. 指标（Metrics）

### 2.1 关键指标
- 成功率：任务完成率、验证通过率
- 质量：回滚次数、补丁冲突率
- 效率：每任务工具调用次数、平均耗时
- 性能：索引构建耗时、grep/语义检索耗时

### 2.2 分布与标签
- `workspace_size_bucket`
- `project_type`
- `tool_name`
- `error_code`

## 3. 链路追踪（Tracing）

### 3.1 Span 建模建议
- `task.run`（根 span）
  - `context.build`
  - `plan.generate`
  - `tool.call:<name>`（多次）
  - `verify.run`

## 4. 回放（Replay）

### 4.1 记录内容
- 用户输入
- ContextPack
- 模型输出（含工具调用指令）
- 工具调用的请求/结果
- 文件变更 patch/diff

### 4.2 回放用途
- 复现 bug
- 回归评测
- 审计取证

## 5. MVP 实现建议
- 先做：结构化工具日志 + trace_id
- 再做：回放包导出（单文件 tar/zip）
- 最后做：指标面板与自动评测


