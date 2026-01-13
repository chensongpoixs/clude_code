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
- [ ] **规划器 (Planner)**:
    - 引导模型生成显式 `Plan` (任务列表)。
- [ ] **显式状态机**:
    - `INTAKE` -> `PLANNING` -> `EXECUTING` -> `VERIFYING` -> `DONE`。
- [ ] **重规划机制 (Re-planning)**:
    - 当任务失败或环境变更时，自动更新 `Plan`。
- [ ] **中断与续跑**:
    - 支持保存 Session 状态，Ctrl+C 后可恢复执行。

---

## 阶段四：感知增强与扩展性 - P1
- [ ] **检索融合 (Unified Retriever)**:
    - 融合 grep、语义、Repo Map 的加权搜索。
- [ ] **工具插件系统**:
    - 支持从外部脚本加载自定义工具。
- [ ] **LSP 集成**:
    - 利用 Language Server 提供精确的符号跳转和引用分析。
- [ ] **企业级安全策略**:
    - 远程策略下发、更细粒度的 RBAC 权限控制。

---

## 实施指南
- **契约先行**: 在开发新模块前，先更新 `PROTOCOLS.md` 定义数据格式。
- **测试驱动**: 为每个 Tool 和编排逻辑编写本地 Mock 测试。
- **审计记录**: 所有新增步骤必须产生对应的 `Audit` 和 `Trace` 日志。

