# 99｜模块索引总表（依赖关系与接口清单）

本表用于把所有模块“收口”成一张可落地的开发蓝图：每个模块的职责、主要接口、依赖与里程碑。

## 1. 模块清单（按层）

### 1.1 交互层（CLI/UX）
- `docs/13-ui-cli-ux.md`
- **依赖**：Orchestrator、Tool Registry、Audit Log
- **产物**：命令行会话、确认交互、流式输出渲染
- **补充能力（已落地）**：
  - `-p/-c/-r`：非交互执行与会话恢复（`.clude/sessions/`）
  - `.clude/commands/*.md`：项目级自定义命令（参数校验 + 命令级权限声明）
  - `--live-ui opencode(textual)`：OpenCode 风格 TUI（多窗格滚动；对话/输出默认日志流；控制面板显示 LLM 请求进度；事件窗格强摘要 + JSON）

### 1.2 代理编排层（Orchestrator）
- `docs/01-e2e-flow-and-state-machine.md`
- **依赖**：Context Builder、Planner、Tooling、Policy、Observability
- **产物**：状态机、重试/降级/回滚、执行闭环

### 1.3 上下文层（Context & Prompting）
- `docs/04-context-and-prompting.md`
- **依赖**：Retrieval、Memory、Observability
- **产物**：ContextPack、预算裁剪、提示词模板

### 1.4 索引检索层（Indexing/Retrieval）
- `docs/03-repo-indexing.md`
- **依赖**：File Catalog、Grep、(Semantic Index)、(Symbol Index)
- **产物**：召回命中、文件片段读取

### 1.5 工具层（Tooling）
- `docs/02-tool-protocol.md`
- **依赖**：Policy Engine、Sandbox、Audit Log
- **产物**：统一工具协议、schema 校验、工具注册表

### 1.6 编辑与变更层（Editing）
- `docs/06-code-editing-and-patching.md`
- **依赖**：File IO 工具、Policy、Audit
- **产物**：apply_patch、冲突处理、undo_patch

### 1.7 运行时层（Runtime）
- `docs/07-runtime-and-terminal.md`
- **依赖**：Policy、Sandbox、Observability
- **产物**：命令执行、输出裁剪、后台任务（可选）

### 1.8 质量层（Verification）
- `docs/08-lint-test-build.md`
- **依赖**：Command Runner、Project Detector、Observability
- **产物**：验证策略、结构化错误、自动修复（可选）

### 1.9 Git 层（可选）
- `docs/09-git-workflow.md`
- **依赖**：Policy、Audit、Summarizer
- **产物**：diff/commit/branch、PR 文案

### 1.10 记忆层（Memory）
- `docs/10-memory-and-knowledge.md`
- **依赖**：Policy（敏感信息）、Observability（审计）
- **产物**：workspace/user 记忆读写、生命周期治理

### 1.11 安全层（Security/Policy）
- `docs/11-security-and-policy.md`
- **依赖**：无（底座模块）
- **产物**：策略引擎、确认机制、敏感信息防护

### 1.12 可观测层（Observability）
- `docs/12-observability.md`
- **依赖**：无（底座模块）
- **产物**：日志/指标/Tracing/回放

### 1.13 插件生态（可选）
- `docs/14-plugin-ecosystem.md`
- **依赖**：Tool Registry、Policy、Sandbox
- **产物**：插件 manifest、工具扩展、兼容管理

### 1.14 部署运维（Deployment）
- `docs/15-deployment.md`
- **依赖**：Config、Observability、Policy
- **产物**：配置体系、doctor、升级与治理

## 2. 关键内部接口（建议先实现的最小集合）

### 2.1 Orchestrator → Tooling
- `tool.call(name, args) -> ToolCallResult`
- `tool.confirm(scope) -> allow/deny`

### 2.2 Orchestrator → Context
- `context.build(task) -> ContextPack`

### 2.3 Context → Retrieval
- `retrieval.grep(...)`
- `retrieval.semanticSearch(...)`（可选）
- `retrieval.readSnippet(path, range)`

### 2.4 Orchestrator → Verification
- `verify.run(policy) -> VerificationResult`

## 3. MVP 里程碑（推荐顺序）

### 3.1 MVP（先跑起来）
- Tooling：read/list/grep/apply_patch/run_cmd（受 policy）
- Orchestrator：状态机 + 计划 + 执行闭环
- Verification：最基本 lint/test 命令编排
- Observability：工具结构化日志 + trace_id

### 3.2 v1（对标主流）
- 语义检索索引（异步 + 降级）
- 更强冲突处理与回滚
- Git 工作流 + PR 文案
- 更完善安全策略与敏感信息防护

---

## 4. 全仓治理与开发计划（执行清单）

- `docs/16-development-plan.md`：全仓模块逻辑流程、问题清单（P0/P1/P2）、对标业界改造建议与验收标准。


