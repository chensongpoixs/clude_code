# 00 | 架构总览：Code Agent CLI 设计白皮书

> **Clude Code** (Open Source Implementation of Claude Code / 开源版 Clude Code 实现)  
> 打造企业级、本地化、高可控的 AI 编程助手基础设施。

---

## 1. 产品愿景 (Mission & Vision)

**Clude Code** 旨在复刻并超越业界顶尖 Code Agent (如 Claude Code) 的核心体验，提供一套**本地优先 (Local-First)**、**隐私安全**且**高度可控**的 CLI 编程代理。它通过深度理解代码仓库上下文，自动化执行从“需求理解”到“代码落地”的完整工程闭环。

### 1.1 核心价值主张
*   🛡️ **Privacy by Design**: 数据不出域，基于 `llama.cpp` 本地模型推理。
*   ⚙️ **Control Plane**: 严格的 ToolSpec 契约与权限沙箱，杜绝不可控行为。
*   🧠 **Deep Context**: 融合 AST 语义分析与向量检索 (RAG)，精准定位代码逻辑。
*   👁️ **Observability**: 全链路 Trace/Audit，每一次决策都可追溯、可回放。

---

## 2. 功能矩阵 (Capabilities Matrix)

| 维度 | 核心能力 | 技术栈 | 落地状态 |
| :--- | :--- | :--- | :--- |
| **感知层** (Perception) | 📂 **仓库拓扑** | `universal-ctags`, `repo-map` | ✅ Ready |
| | 🔍 **混合检索** | `ripgrep`, `LanceDB`, `Hybrid Search` | ✅ Ready |
| | 🧩 **语义解析** | `tree-sitter`, `AST Chunking` | ✅ Ready |
| **决策层** (Reasoning) | 🧠 **任务编排** | `ReAct Loop`, `Explicit Planning` | ✅ Ready |
| | 🚦 **意图识别** | `Heuristic Classifier`, `Prompt Gate` | ✅ Ready |
| | 🛡️ **安全策略** | `RBAC Policy`, `Command Denylist` | ✅ Ready |
| **执行层** (Action) | ⚡ **工具调用** | `ToolSpec`, `Pydantic Validation` | ✅ Ready |
| | 📝 **精准编辑** | `Fuzzy Patch`, `Atomic Write` | ✅ Ready |
| | 🧪 **验证闭环** | `Auto-Test`, `Linter Feedback` | ✅ Ready |
| **交互层** (Interaction) | 🖥️ **TUI 界面** | `Textual`, `Rich`, `Streaming UI` | ✅ Ready |
| | 💬 **命令系统** | `Slash Commands`, `Custom Macros` | ✅ Ready |

---

## 3. 系统架构 (System Architecture)

### 3.1 分层架构图

![System Architecture](../src/assets/architecture_overview.svg)

### 3.2 关键模块职责

*   **交互层 (UI/CLI)**: 负责用户意图捕获、流式渲染 (Streaming UI) 与确认交互。
*   **代理层 (Orchestrator)**: 核心状态机，维护 `PLANNING` -> `EXECUTING` -> `VERIFYING` 的生命周期。
*   **上下文层 (Context Builder)**: 动态组装 `System Prompt`，智能裁剪 Token 预算，注入 Repo Map 与 RAG 摘要。
*   **工具层 (Tooling)**: 标准化工具协议 (Tool Protocol)，封装 `read`, `write`, `exec` 等原子能力。
*   **索引层 (Indexing)**: 后台异步构建语义索引与符号索引，提供毫秒级代码召回。

---

## 4. 设计原则 (Design Principles)

### 4.1 可控性优先 (Control First)
*   **Default Deny**: 默认拒绝高风险操作（写文件、执行命令），需显式确认或策略放行。
*   **Plan before Action**: 复杂任务必须先输出 `Plan` (JSON)，用户认可后再执行。

### 4.2 极致可观测 (Radical Observability)
*   **Trace ID**: 每一轮对话分配唯一 UUID，贯穿全链路。
*   **Audit Log**: 结构化记录每一次工具调用的输入、输出、耗时与 Error Stack。

### 4.3 契约驱动 (Contract Driven)
*   **ToolSpec**: 工具定义即文档，单一真实源 (Single Source of Truth)。
*   **Schema Validation**: 运行时强校验 LLM 输出，自动纠错重试。

---

## 5. 技术文档索引 (Technical Index)

> 汇集全仓深度技术分析与决策记录，方便架构师与开发者查阅。

### 5.1 架构与决策
*   **[项目进度与业界对齐报告 (NEW)](./PROJECT_STATUS.md)**: 当前版本功能完成度与业界主流 Code Agent (Claude Code, Aider) 的横向对比。
*   **[工业级代码工程规范](./CODE_SPECIFICATION.md)**: 强制执行的开发准则、注释模板、配置管理与**提示词外置**约定。
*   **[Agent 决策链路审计与评分 (P0)](./17-agent-decision-audit.md)**: 深度架构审计，包含 Trace ID/控制协议/重规划的优缺点分析。
*   **[业界 Code Agent 技术白皮书](./technical-reports/industry-whitepaper.md)**: 包含详细的原理图、流程图和最佳路径分析。
*   **[健壮性复盘报告](./technical-reports/robustness-review.md)**: 系统稳定性分析与关键修复点。

### 5.2 核心模块深挖
*   **RAG/Knowledge（检索增强/知识库）**:
    *   [RAG 深度调优路线图](./technical-reports/rag-tuning.md): Hybrid Search, AST Chunking, Rerank 策略。
*   **Orchestrator（编排器）**:
    *   [编排层健壮性分析](./technical-reports/orchestrator-robustness.md): 状态机与异常处理机制。
    *   [规划与执行层落地报告](./technical-reports/orchestrator-implementation.md): Planning & Execution 实现细节。
*   **Verification（验证/自愈闭环）**:
    *   [自动验证分析](../src/clude_code/verification/ANALYSIS_REPORT.md): 验证闭环与自愈机制。

---
