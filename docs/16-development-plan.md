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

### 4.0 Claude Code 深度对标计划（补齐业界 GAP）

| 模块 | 对标功能 | 状态 | 优先级 | 计划/目标 |
| :--- | :--- | :--- | :--- | :--- |
| **Mode** | `claude -p` (Print 模式) | ✅ 已完成 | P1 | 支持单次 Prompt 执行并退出（脚本集成） |
| | `claude -c/-r` (会话恢复) | ✅ 已完成 | P1 | `.clude/sessions/` 持久化历史；`-c` 继续最新会话，`-r` 恢复指定会话 |
| **UI/UX** | `/slash` 命令系统 | ✅ 已完成 | P0 | REPL 内 `/help`, `/config`, `/permissions` 等 |
| | 增强版 Claude Code UI | ✅ 已完成 | P0 | 左侧滚动 + 右侧面板 + 阶段块布局 |
| | OpenCode 风格 TUI（Textual，多窗格滚动） | ✅ 已完成（可选依赖） | P1 | `--live-ui opencode`：多窗格、鼠标滚轮滚动历史、减少整屏刷新 |
| **Policy** | `allowedTools` / `disallowedTools` | ✅ 已完成 | P0 | 策略引擎强制拦截 |
| | `CLUDE.md` (项目记忆) | ✅ 已完成 | P1 | 自动搜索并注入 System Prompt |
| **Plugins** | 自定义命令扩展 | ✅ 已完成 | P1 | 支持从 `.clude/commands/*.md` 加载自定义命令；支持参数校验（`args/required/usage`）与命令级权限声明（`allowed_tools/disallowed_tools/allow_network`） |

### 4.0.1 Claude Code 差距清单（仅针对 `clude chat --live --live-ui enhanced`）

> 说明：这里只列 **Claude Code 终端体验**（产品级）里，我们还没对齐的部分。对标来源：[anthropics/claude-code](https://github.com/anthropics/claude-code)

#### Gap-A：Git 工作流（Claude Code 强项）
- **差距**：缺少“git 一等公民工作流”（diff/commit/branch/PR 文案/变更审阅）与对应事件在 live UI 的阶段化呈现。
- **现状模块**：暂无 `git/*` 专用模块；仅有 `run_cmd` + policy 约束的通用能力。
- **P1 验收标准**：
  - 新增 `git_*` 工具（至少：`git_status/git_diff/git_commit`）或一套 git workflow 子命令
  - live UI 能显示“变更摘要→审阅→提交”的阶段块（含失败原因与回滚建议）

#### Gap-B：输入侧交互（终端内编辑体验）
- **差距**：输入区缺少更强的终端编辑与交互（历史搜索、宏命令、可视化确认、可展开详情）。
- **现状模块**：`cli/shortcuts.py` 有基础快捷键；live UI 侧重输出呈现。
- **P1 验收标准**：
  - 自定义命令支持“补全提示/用法提示”更完整（已做基础校验，下一步补 completion）
  - tool_result 支持“摘要 + 可展开详情”（至少在 classic 输出模式提供 `--show-details`）

#### Gap-C：插件生命周期（生态化）
- **差距**：缺少 Claude Code 那类“插件安装/启用/禁用/版本兼容”的产品化流程（我们目前更多是“内置插件/声明式插件”）。
- **现状模块**：`plugins/` 已有 registry 与沙箱执行，但缺少“用户侧生命周期管理命令”与统一 UX。
- **P2 验收标准**：
  - `clude plugins list|enable|disable|install`（最小集）
  - 插件版本/host_version 不兼容时能明确拒绝并给出修复建议

#### Gap-D：成本/用量与反馈闭环
- **差距**：从“可用的估算”升级为“更产品化/更可信的成本闭环”（例如：真实 token 使用、可导出报表、异常归因）。
- **现状模块（已落地）**：
  - ✅ `SessionUsage` 会话级统计（LLM 请求次数/耗时、token 估算、工具调用/失败）
  - ✅ `/cost`：实时查看本会话用量/成本（估算）
  - ✅ `/bug`：报告自动附带 session_id、last_trace_id、以及用量摘要（估算）
- **P2 验收标准（剩余差距）**：
  - 对接“真实 token/usage”（服务端返回或可计算）并区分 prompt/completion 的真实口径
  - 支持导出（JSON/Markdown）与按 turn/trace_id 归因（哪个步骤最耗）

### 4.1 P0 迭代（稳定性优先，先保证“能用且一致”）

> 本节从 P0 开始补齐两类信息：
> - **现有代码实现原理**：当前代码真实的调用链路、关键文件与关键机制。
> - **在现有代码上做 P0 完善的思考过程**：为什么要这么改、改什么、怎么验收。

#### P0-1 统一工具契约：ToolSpec 单一真实源

##### 现有实现原理（现状代码怎么工作的）

- **工具事实来源（ToolSpec Registry）**：`src/clude_code/orchestrator/agent_loop/tool_dispatch.py`
  - **ToolSpec 定义**：工具的事实字段集中在 ToolSpec：`name/summary/args_schema/example_args/side_effects/visible_in_prompt/callable_by_model/handler`。
  - **系统提示词工具清单渲染**：`render_tools_for_system_prompt()` 遍历 ToolSpec，生成 `SYSTEM_PROMPT` 的“可用工具清单”。
  - **运行时参数强校验**：`ToolSpec.validate_args()` 依据 `args_schema` 动态创建 Pydantic 模型进行强校验（含 default 生效、enum 检查、extra forbid 等），失败返回 `E_INVALID_ARGS`。
  - **分发入口**：`dispatch_tool()` 负责：
    - 未知工具 → `E_NO_TOOL`
    - `callable_by_model=False` 的内部项 → `E_NO_TOOL`
    - 参数校验失败 → `E_INVALID_ARGS`
    - 校验通过 → `spec.handler(loop, validated_args)`

- **工具生命周期（确认/策略/审计/验证闭环）**：`src/clude_code/orchestrator/agent_loop/tool_lifecycle.py`
  - 依据 `side_effects` 决策确认与策略：
    - `write`：按 `cfg.policy.confirm_write` 询问用户
    - `exec`：先 `evaluate_command()` 安全评估，再按 `cfg.policy.confirm_exec` 询问用户
  - 写入审计：`AuditLogger`（`.clude/logs/audit.jsonl`）
  - 修改类工具成功后触发选择性验证：`Verifier.run_verify(modified_paths=...)`

- **工具底层实现**：
  - 文件/搜索/补丁/命令：`src/clude_code/tooling/local_tools.py` → `src/clude_code/tooling/tools/*`
  - 编排器能力类工具（如语义检索）：handler 调 `AgentLoop` 能力方法（避免把 RAG 细节堆到 LocalTools）

##### P0 完善思考过程（为什么要改、改什么、怎么验证）

**问题本质**：只要 ToolSpec、handler、底层实现、文档中任意一处不一致，就会出现“工具看起来可用但不生效”“模型按 schema 传参被忽略”“不同 UI/入口行为不同”等割裂。  
业界做法是：**ToolSpec 必须是唯一真实源（Single Source of Truth）**，其它层只能引用它，不能维护第二份“工具事实”。

- **工作项（在现有代码上最小侵入的落地方案）**：
  - 全量检查 ToolSpec 的 `args_schema`、handler 读取字段、底层实现函数签名、`docs/02-tool-protocol.md` 是否一致。
  - 为历史字段保留兼容层（如 `message` → `content`），并标注废弃计划（何时移除、如何提示）。
  - 增加“一键自检”，把契约漂移变成可检测问题（建议新增 `clude doctor --check-tools` 或 `clude tools --validate`）。

- **验收标准**：
  - `clude tools --json --schema` 输出与运行时校验一致
  - 所有工具的 `example_args` 能通过 `validate_args()`
  - 任意工具按 schema 调用不会出现“参数被忽略/无法生效”

#### P0-2 收敛 chat/live 单入口

##### 现有实现原理（现状代码怎么工作的）

- **默认入口**：`src/clude_code/cli/main.py` 的 `clude chat` 当前使用 `src/clude_code/cli/chat_handler.py::ChatHandler`
  - `ChatHandler` 内部创建 `AgentLoop(cfg)`
  - 普通模式：`_run_simple()` → `AgentLoop.run_turn(..., debug=debug)`
  - Live 模式：`_run_with_live()` 使用 `LiveDisplay`，并把 `on_event_wrapper` 传给 `AgentLoop.run_turn(..., on_event=...)`

- **Live UI（50 行面板）**：`src/clude_code/cli/live_view.py::LiveDisplay`
  - 接收事件（如 `llm_request/llm_response/tool_call_parsed/tool_result/display`）
  - 更新面板状态与“思考窗口”
  - `display` 事件用于 Agent 主动输出中间信息（进度/阶段结论）

- **并行存在的增强版链路（潜在分裂风险）**：
  - `src/clude_code/cli/enhanced_chat_handler.py::EnhancedChatHandler`
  - `src/clude_code/cli/enhanced_live_view.py::EnhancedLiveDisplay`
  - 当前默认入口未使用增强版，但代码并行存在，后续很容易出现“某功能只在一条链路修了/加了”的维护分裂。

##### P0 完善思考过程（为什么要改、改什么、怎么验证）

**问题本质**：两套 chat/live 主链路并行时，display、日志、确认交互、事件协议、错误展示都可能出现“只在 A 修复、B 没修复”的分裂。  
业界做法：**默认主路径必须唯一**；增强能力通过开关/注入/配置扩展，而不是长期维护两套主链路。

- **工作项（两条路线二选一即可）**：
  - 路线 A（推荐）：合并增强能力到默认链路  
    把增强 UI 的价值点（细粒度进度/任务）抽为可选组件，注入 `LiveDisplay`，避免第二套主循环。
  - 路线 B：保留增强版但必须显式开关且共享核心  
    CLI 增加 `--ui enhanced`（或配置项）选择 UI；关键约束：共享同一个 `AgentLoop` 与同一套事件协议，不复制粘贴核心逻辑。

- **验收标准**：
  - 同一输入在普通模式与 `--live` 模式下行为一致（仅 UI 呈现不同）
  - `display`、tool 事件、确认交互在所有启用的 UI 模式下行为一致
  - 不存在两份独立的“chat 主循环 + on_event glue code”长期并行维护

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


