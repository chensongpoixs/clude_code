# 开发实现详细路线图 (Modular Implementation Roadmap)

本计划将 Code Agent 的开发拆分为四个关键阶段，重点解决**验证闭环**与**任务规划**。

---

## 阶段一：基础设施与编辑增强（当前）
- [x] **本地 LLM 集成**: 稳定 llama.cpp HTTP 接入。
- [x] **Patch 引擎**: 实现 `apply_patch` 与 `undo_patch`。
- [x] **基础检索**: 集成 ctags (Repo Map) 与 LanceDB (RAG)。
- [ ] **增强 Patch 鲁棒性**:
    1. 实现自动缩进识别。
    2. 增加对“多处相同代码块”的同时替换支持。
- [ ] **集成 Ripgrep**: 优化超大仓库的搜索性能。

---

## 阶段二：验证闭环 (Verification Loop) - ✅ 已完成
- [x] **项目探测 (Detector)**:
    - 识别 `pyproject.toml`, `package.json`, `go.mod` 等。
- [x] **执行器 (Runner)**:
    - 封装 `pytest`, `npm test`, `flake8` 命令。
- [x] **结构化回喂**:
    - 解析错误输出，提取 `file`, `line`, `message`。
- [x] **自愈循环**:
    - Agent 根据验证失败信息自动调用 `apply_patch` 修复。详见 `src/clude_code/verification/IMPLEMENTATION_REPORT_PHASE2.md`。

---

## 阶段三：规划与两级编排 (Planning & Orchestration) - P0
- [x] **规划器 (Planner)**:
    - 已落地 `orchestrator/planner.py`：Plan/Step 的 Pydantic 校验 + 从模型输出中容错提取 JSON。
- [x] **显式状态机**:
    - 已落地 `orchestrator/state_m.py`：`INTAKE` -> `PLANNING` -> `EXECUTING` -> `VERIFYING` -> `DONE`（用于事件上报与可观测）。
- [x] **重规划机制 (Re-planning)**:
    - 已集成到 `agent_loop.py`：步骤失败时触发有限次数重规划（`max_replans`），并熔断防死循环。
- [ ] **中断与续跑**:
    - 仍待实现：保存 Session 状态、Ctrl+C 后恢复执行（需要持久化 Plan/执行游标/最近工具结果）。

### 阶段三实现报告
- ✅ 见 `src/clude_code/orchestrator/IMPLEMENTATION_REPORT_PHASE3.md`

---

## 阶段四：感知增强与扩展性 - ✅ 已完成
- [ ] **检索融合 (Unified Retriever)**:
    - 融合 grep、语义、Repo Map 的加权搜索。（待实现）
- [x] **工具插件系统**:
    - 已落地 `plugins/registry.py`：YAML/JSON 声明式定义 + 子进程沙箱执行 + 参数校验。
- [x] **LSP 集成**:
    - 已落地 `lsp/client.py`：通用 LSP 客户端，支持多语言服务器，精确符号跳转/引用分析。
- [x] **企业级安全策略**:
    - 已落地 `policy/enterprise_policy.py`：RBAC 权限模型 + 远程策略下发 + 企业审计。

### 阶段四实现报告
- ✅ 见 `src/clude_code/PHASE4_IMPLEMENTATION_REPORT.md`

---

## 实施指南
- **契约先行**: 在开发新模块前，先更新 `PROTOCOLS.md` 定义数据格式。
- **测试驱动**: 为每个 Tool 和编排逻辑编写本地 Mock 测试。
- **审计记录**: 所有新增步骤必须产生对应的 `Audit` 和 `Trace` 日志。

---

## 近期治理计划补充（全仓审计结论 → 可执行改造项）

> 目标：把“全仓模块逻辑梳理 + 问题清单（P0/P1/P2）+ 对标业界建议”映射到路线图，形成可验收的迭代计划。
>
> 详单见：`docs/16-development-plan.md`

### P0（立刻修：契约一致性与入口收敛）
- **P0-ToolSpec 单一真实源**：统一 ToolSpec schema/handler/实现/文档，避免“工具看起来可用但不生效”的断裂。
- **P0-chat/live 单入口**：收敛多套 chat/live 实现，避免行为分裂（增强能力走 feature flag / 注入式扩展）。

### P1（健壮性治理：日志/异常/配置/注册表合流）
- **异常可观测性统一**：任何异常至少写 file-only；用户可见路径输出友好摘要并保留 trace_id。
- **配置一致性**：修正默认值/约束矛盾；doctor/启动输出关键配置摘要（RAG device、embedding 模型、索引状态）。
- **Tool Registry 合流**：以 ToolSpec Registry 为唯一事实源，其它 registry 仅做视图/统计。

### P2（业界对标增强：质量门禁与 RAG 深度调优）
- **质量门禁落地**：ruff/mypy/tests/CI/pre-commit 固化，防止迭代回退。
- **RAG 深度调优**：AST/tree-sitter 分块 + chunk 元数据（符号/作用域）+ 检索融合（grep/semantic/repo map）。

