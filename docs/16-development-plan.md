# 16｜全仓模块逻辑梳理与开发计划（P0/P1/P2）

> 目的：把一次“全仓运行链路审计”的结论固化为**可执行的开发计划**，用于后续迭代的优先级排序、验收标准与工程治理。
>
> 适用范围：`clude-code`（Python CLI Code Agent）全模块：CLI / Orchestrator / Tooling / RAG / LLM / Verification / Policy / Observability / Plugins。

---

## 1. 分析方法（如何得出结论）

本计划的分析遵循业界 Code Agent 工程化做法（对标 Claude Code / Aider / Cursor），采用三步：

- **端到端主链路优先**：先画“用户输入到工具执行到验证到总结”的真实调用链，确认事件/数据如何流动。
- **按层拆模块边界**：验证分层是否清晰、是否存在重复入口导致行为分裂。
- **契约一致性检查**：重点排查 ToolSpec（schema/默认值/可调用性/副作用）、事件协议、日志与错误码是否一致。

---

## 2. 端到端逻辑流程（E2E）

### 2.1 入口层（CLI）
- `clude chat`：进入会话循环（普通输出 / `--live` 实时界面）。
- `clude doctor`：环境诊断、依赖检查、LLM 连通性检查。
- `clude tools`：输出工具清单（同源于 ToolSpec Registry）。

### 2.2 编排层（Orchestrator）
核心入口：`src/clude_code/orchestrator/agent_loop/agent_loop.py::AgentLoop.run_turn`

关键机制：
- 统一事件出口 `_ev`：负责写 `trace.jsonl`（debug 时）、聚合 events、推送 live UI。
- 规划-执行两级编排：`planning.py` 生成 Plan；`execution.py` 按步骤循环执行；必要时 ReAct fallback。

### 2.3 工具层（Tooling）
链路：`ToolSpec Registry (tool_dispatch.py)` → `tool_lifecycle.py`（确认/策略/审计/执行/验证闭环）→ `tooling/local_tools.py` → `tooling/tools/*`。

### 2.4 RAG（Indexing/Retrieval）
- `IndexerService` 后台增量索引：扫描 mtime/hash → 智能分块 → 批量 embedding → LanceDB 写入。
- `semantic_search`：embed_query → vector_store.search → 返回命中片段。

### 2.5 验证闭环（Verification）
- `Verifier.run_verify(modified_paths=...)`：探测语言/命令 → 选择性测试 → 结构化解析错误 → 返回给编排器用于自愈或总结。

---

## 3. 发现的问题清单（按严重度 P0/P1/P2）

### 3.1 P0（必须立刻修：会导致行为错误/体验断裂/契约失真）
- **工具契约不一致（ToolSpec ↔ handler ↔ 实现 ↔ 文档）**  
  - 风险：模型按 schema 传参但 handler 读不同字段，或实现逻辑分叉导致“看起来有工具但不工作”。  
  - 典型例：`display` 工具曾出现字段不一致导致“不显示”（已在代码侧做过一次统一与兼容字段保留）。

- **重复入口导致行为分裂（多套 chat/live 实现并存）**  
  - 风险：同一功能在 A 入口生效，在 B 入口失效；用户体验不稳定；维护成本指数级上升。  
  - 目标：默认链路必须唯一；增强版能力通过 feature flag 或直接合并替换。

### 3.2 P1（强烈建议尽快修：健壮性/可维护性缺口，复杂场景会放大）
- **异常可观测性不完全一致**  
  - 目标：任何异常至少写入 file-only 日志；用户可见路径输出友好摘要（同时保留 trace_id）。

- **配置约束与默认值矛盾**  
  - 风险：默认值超出约束上限或含义不清，导致运行行为与用户预期不一致。  
  - 目标：统一 default / 上限 / 文档描述，并在启动时给出配置诊断（doctor/启动日志）。

- **工具注册表重复建设**  
  - 风险：存在多个 registry（工具事实分裂），导致 prompt 列表、可调用工具、metrics 统计对象不一致。  
  - 目标：ToolSpec Registry 作为“唯一真实源”；其它 registry 仅做视图/统计，不再维护第二份工具集合。

### 3.3 P2（中长期：质量门禁/工程化/性能演进）
- **质量门禁未完全落地**（formatter/lint/type/test/CI/pre-commit）  
  - 目标：把质量门禁变成 CI 必选项，防止迭代回退。

- **RAG 分块策略偏启发式**  
  - 目标：逐步引入 AST/tree-sitter 分块（至少 Python/TS/Go），并为 chunk 加“符号/作用域”元数据，提升召回稳定性与可解释性。

---

## 4. 开发计划（按优先级与验收标准）

### 4.1 P0 迭代（稳定性优先，先保证“能用且一致”）

#### P0-1 统一工具契约：ToolSpec 单一真实源
- **工作项**：
  - 全量检查 ToolSpec 的 `args_schema`、handler 读取字段、实际实现函数签名、`docs/02-tool-protocol.md` 是否一致。
  - 为历史字段保留兼容层（如 `message` → `content`），并标注废弃计划。
- **验收标准**：
  - `clude tools --json --schema` 输出与运行时校验一致。
  - 任意工具按 schema 调用不会出现“参数被忽略/无法生效”的情况。

#### P0-2 收敛 chat/live 单入口
- **工作项**：
  - 明确默认入口文件（建议只保留一套 chat handler + live view）。
  - 增强版能力通过配置/flag 注入，而不是并行存在两套主路径。
- **验收标准**：
  - 同一输入在普通模式与 `--live` 模式下的行为一致（仅 UI 呈现不同）。

### 4.2 P1 迭代（健壮性与可维护性）

#### P1-1 异常处理与日志规范统一
- **工作项**：
  - 建立统一的异常记录助手（控制台摘要 + file-only 详细堆栈）。
  - 后台任务（索引）增加 rate limit（避免刷屏）与健康状态输出（便于诊断）。
- **验收标准**：
  - 任意异常可在 `.clude/logs/*.log` / `trace.jsonl` / `audit.jsonl` 中复现定位。

#### P1-2 配置一致性与启动诊断
- **工作项**：
  - 修正默认值/约束矛盾；补齐 doc。
  - `doctor`/启动阶段输出关键配置摘要（尤其是 RAG device、embedding 模型、索引状态）。
- **验收标准**：
  - 配置无矛盾；不合理配置能被 doctor 明确提示。

#### P1-3 Tool Registry 去重合流
- **工作项**：
  - 统一“工具事实来源”为 ToolSpec Registry。
  - metrics/分类在同一 registry 的视图层实现，避免维护两份工具集合。
- **验收标准**：
  - 工具列表、prompt 工具清单、dispatch 可调用工具三者完全一致。

### 4.3 P2 迭代（性能与业界对标提升）

#### P2-1 质量门禁落地
- **工作项**：引入并固化 `ruff`/`mypy`/基础 tests（至少覆盖解析/策略/patch/工具 schema）。
- **验收标准**：CI 必过；本地一键验证可复现。

#### P2-2 RAG 深度调优：语法分块 + 元数据
- **工作项**：tree-sitter/AST 分块、chunk 元数据（符号/作用域）、检索融合（grep + semantic + repo map）。
- **验收标准**：召回更稳定；命中片段更可解释；大仓性能可控。

---

## 5. 推荐的推进节奏（落地建议）
- **先 P0 再 P1**：先消除“行为分裂/契约失真”，再做健壮性治理。
- **每个工作项都带验收**：避免“改了很多但不可验证”的迭代。
- **文档与工具同源**：ToolSpec 更新必须同步更新 `docs/02-tool-protocol.md` 与示例。


