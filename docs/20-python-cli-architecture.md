# 20｜Python 纯 CLI 落地架构（包结构 + 模块职责）

本章给出“Claude Code/Code Agent CLI”的 Python 落地建议：包结构、模块边界、关键对象模型（与 JSON Schema 对齐）。

## 1. 技术选型（推荐）

- **Python**：3.11+（更好类型与性能）
- **类型/校验**：Pydantic v2（用于把 JSON Schema 对齐成模型）
- **CLI**：Typer（基于 Click，体验好）
- **结构化日志**：`structlog` 或标准库 `logging` + JSON formatter
- **配置**：`pydantic-settings`（可合并 env + 文件 + CLI 参数）
- **JSON Schema**：仓库内固定版本的 `schemas/*.json`，作为“协议真相源”（source of truth）

> 说明：本仓库先以“文档 + schema + 目录骨架”落地，模型（LLM）接入可后续替换（OpenAI/Anthropic/本地模型网关均可）。

## 2. 分层与包职责（与 docs/99 对齐）

### 2.1 CLI 层：`src/clude_code/cli/`
- 命令入口、参数解析、会话 loop、渲染与确认
- 不直接做 IO/exec/写文件，全部走 `tooling`

### 2.2 Orchestrator：`src/clude_code/orchestrator/`
- 状态机（INTAKE/CONTEXT/PLAN/EXEC/VERIFY/SUMMARY）
- 重试/降级/回滚编排
- 产出 Plan、驱动工具调用

### 2.3 Context：`src/clude_code/context/`
- ContextPack 组装、token 预算裁剪、上下文摘要

### 2.4 Retrieval/Index：`src/clude_code/retrieval/`
- file catalog、grep adapter、（可选）semantic index

### 2.5 Tooling：`src/clude_code/tooling/`
- Tool Registry（工具注册表）
- 工具协议（schema 校验）
- 统一 ToolCall 执行入口

### 2.6 Policy/Sandbox：`src/clude_code/policy/`
- 权限与规则评估：ALLOW/DENY/REQUIRE_CONFIRMATION
- 路径边界、防敏感信息、命令 allowlist/denylist

### 2.7 Runtime：`src/clude_code/runtime/`
- 命令执行、输出裁剪、后台任务（可选）

### 2.8 Verification：`src/clude_code/verification/`
- 探测项目、选择 lint/test/build 命令、结构化结果

### 2.9 Observability：`src/clude_code/observability/`
- trace_id、结构化日志、审计日志写入、回放包（v1）

### 2.10 Storage：`src/clude_code/storage/`
- `.clude/` 目录管理：audit、memory、index、replay

### 2.11 Memory：`src/clude_code/memory/`
- workspace/user 记忆读写（显式写入）

## 3. “协议优先”的开发方式（强烈建议）

1. 先写 `schemas/*.json`
2. 用 Pydantic 模型把 schema 固化到类型系统
3. 工具层/编排层全部只吃这些模型对象
4. 审计与回放直接存 schema 对象的 JSON（可回放/可扩展）


