# 16 | 工程演进路线图 (Engineering Roadmap / Roadmap=路线图)

> **Status (状态)**: 🟢 Active Development (持续开发中 / Active Development=持续开发)  
> **Focus (当前重点)**: P0 Infrastructure Hardening (基础设施加固 / Hardening=加固：Traceability/可追溯性 & Protocol Stability/协议稳定性)

本路线图基于全仓深度审计结论，旨在构建业界顶尖的 Code Agent 基础设施。

---

## 1. 核心里程碑 (Milestones / Milestone=里程碑)

| Milestone（里程碑） | Theme（主题） | Status（状态） | ETA（预计时间） |
| :--- | :--- | :--- | :--- |
| **M1: MVP+** | 基础闭环 (CLI + Edit + Verify) | ✅ **Completed** | Q4 2025 |
| **M2: Robustness** | **决策链路治理 (Trace ID + Protocol)** | 🔄 **In Progress** | Q1 2026 |
| **M3: Intelligence（智能化）** | RAG Deep Tuning（RAG 深度调优） + Memory（记忆） | ⏳ Planned（已规划） | Q2 2026 |
| **M4: Product（产品化）** | Git Workflow（Git 工作流） + Plugin Ecology（插件生态） | ⏳ Planned（已规划） | Q3 2026 |

---

## 2. 重点攻坚任务 (Priority Tasks / Priority=优先级 & Task=任务)

### 2.1 P0: 基础设施加固 (Based on Audit / Audit=审计)

> 来源：`docs/17-agent-decision-audit.md`

#### P0-1 Trace ID 稳定性治理
*   **Problem（问题）**: `hash()` 依赖随机种子，跨进程不一致，导致日志/Bug 无法归因（Bug=缺陷/问题）。
*   **Goal（目标）**: 引入 `uuid4`，确保全链路唯一标识。
*   **Progress（进度）**:
    *   [x] 引入 `uuid` 标准库
    *   [x] 贯穿 `AgentLoop` -> `_ev` -> `Audit` -> `UI`
    *   [x] 修复 `/bug` 报告归因（trace_id 贯穿与展示）

#### P0-2 控制协议结构化
*   **Problem（问题）**: `STEP_DONE` 字符串匹配易误触，协议脆弱。
*   **Goal（目标）**: 升级为 Strict JSON Envelope（严格 JSON 信封协议）。
*   **Progress（进度）**:
    *   [x] 定义 `{"control": "step_done"}` / `{"control":"replan"}` Schema（控制信号 Schema）
    *   [x] 升级 `Execution` 解析逻辑（优先 JSON，失败兼容旧字符串并告警）
    *   [x] 更新 System Prompt 约束（强制控制 JSON，禁止 STEP_DONE/REPLAN 自由文本）

#### P0-3 局部重规划 (Plan Patching)
*   **Problem（问题）**: 全量重写 Plan（计划）成本高且丢失上下文。
*   **Goal（目标）**: 实现 `PlanPatch`（计划补丁）增量修补。
*   **Progress（进度）**:
    *   [ ] 定义 `PlanPatch` 数据结构
    *   [ ] 实现 `Planner.patch_plan()`
    *   [ ] 优化重规划 Prompt

### 2.2 P1: 健壮性提升 (Robustness / Robustness=健壮性)

#### P1-1 异常处理规范化
*   **Goal（目标）**: 统一 Exception Handling（异常处理），杜绝 `pass` 吞没异常。
*   **Status（状态）**: ⏳ Pending（待开始）

#### P1-2 Tool Registry 去重
*   **Goal（目标）**: 确立 ToolSpec 为 Single Source of Truth（单一真实源），移除冗余定义。
*   **Status（状态）**: ⏳ Pending（待开始）

### 2.3 P2: 体验与生态 (UX & Ecosystem / UX=用户体验 & Ecosystem=生态)

#### P2-1 RAG 深度调优
*   **Goal（目标）**: Tree-sitter Chunking（基于语法树分块）+ Hybrid Search（混合检索）。
*   **Status（状态）**: 🔄 In Progress（进行中）(Chunking 完成，Rerank 调优中)

#### P2-2 Git 工作流集成
*   **Goal（目标）**: 实现 `git` 一等公民体验 (Auto Commit=自动提交, PR Review=PR 审查)。
*   **Status（状态）**: ⏳ Planned（已规划）

---

## 3. 对标 Claude Code 差距清单 (Gap Analysis / Gap=差距)

| Feature Area（能力域） | Claude Code Capability（能力项） | Clude Code Status（当前状态） | Plan（计划） |
| :--- | :--- | :--- | :--- |
| **UX（用户体验）** | Slash Commands（斜杠命令, `/help`） | ✅ Parity（对齐） | - |
|  | Enhanced TUI（增强终端界面） | ✅ Parity（对齐） | OpenCode TUI 已落地 |
| **Mode（模式）** | `-p` (Print Mode=打印模式) | ✅ Parity（对齐） | - |
|  | `-c/-r` (Session Resume=会话续跑/恢复) | ✅ Parity（对齐） | - |
| **Logic（逻辑）** | **Repo Context (200k=大上下文)** | ⚠️ **Gap（差距）** | 需引入 Memory/Summarizer（记忆/摘要器） |
| **Workflow（工作流）** | **Git Integration（Git 集成）** | ❌ **Missing（缺失）** | P2 重点建设 |
| **Cost（成本）** | Usage Attribution（用量归因） | ⚠️ **Partial（部分完成）** | 已有 Session 统计，缺归因 |

---

## 4. 交付质量标准 (Quality Gates / Gate=门禁)

*   ✅ **Linting（代码规范检查）**: `ruff` check passed.
*   ✅ **Typing（类型检查）**: `mypy` strict mode passed.
*   ✅ **Testing（测试）**: Core logic unit tests passed.
*   ✅ **Documentation（文档）**: ToolSpec & Protocols updated.

---
