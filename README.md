# clude-code: 业界级本地编程代理 (Code Agent CLI)

**clude-code** 是一个受 Claude Code 启发、专注于本地化落地的编程代理 CLI。它通过一套闭环的 Agent 编排逻辑，使本地模型（通过 `llama.cpp`）能够理解代码库、规划任务、执行高精度补丁编辑、并进行审计追溯。

本仓库沉淀了从**功能分析**、**架构设计**到**模块化实现**的全过程文档与源码。

> 📖 **[技术白皮书与模块进度总览](./src/README.md)** (开发者必读)

---

## 1. 核心特性 (Key Features)

| 特性 | 说明 | 状态 |
| :--- | :--- | :--- |
| **本地优先 (Local-First)** | 深度集成 `llama.cpp` HTTP API，保护隐私，无须云端 Token。 | ✅ 已落地 |
| **精准编辑 (Patch Engine)** | 借鉴 Aider 的 `Search-Replace` 块逻辑，支持 `apply_patch` 与 `undo_patch`。 | ✅ 已落地 |
| **仓库感知 (Repo Map)** | 基于 `universal-ctags` 的符号拓扑，让 Agent 拥有全局架构视野。 | ✅ 已落地 |
| **语义 RAG (Vector Search)** | 集成 `LanceDB` + `fastembed`，支持 AST 分块与混合检索 (Hybrid Search)。 | ✅ 已落地 |
| **交互体验 (TUI)** | 支持 **OpenCode 风格 TUI** (多窗格滚动) 和 **Claude Code 风格 CLI**。 | ✅ 已落地 |
| **安全审计 (Audit Trace)** | 全量记录工具调用日志与执行轨迹，支持 Hash 级补丁完整性校验。 | ✅ 已落地 |
| **交互式修复 (Auto-Fix)** | `doctor --fix` 能够自动诊断并跨平台安装 `rg`、`ctags` 等外部依赖。 | ✅ 已落地 |

---

## 2. 快速开始 (Quick Start)

### 2.1 环境准备 (PowerShell / Windows)

```powershell
# 1. 创建环境
conda create -n clude_code python=3.11 -y
conda activate clude_code

# 2. 安装项目（含开发模式与 RAG 依赖）
pip install -e ".[rag]"

# 3. 配置 LLM 访问（确保 llama.cpp server 已启动）
$env:CLUDE_WORKSPACE_ROOT="D:\Work\AI\clude_code"
$env:CLUDE_LLM__BASE_URL="http://127.0.0.1:8899"
$env:CLUDE_LLM__API_MODE="openai_compat"
```

### 2.2 启动对话

```powershell
# 1. 诊断环境与缺失工具
clude doctor --fix

# 2. 初始化项目记忆 (可选)
# 交互选择模型并生成 CLUDE.md
clude chat --select-model
/init

# 3. 进入交互式开发对话 (推荐使用 OpenCode TUI)
clude chat --live --live-ui opencode
```

---

## 3. CLI 命令参考

> 完整参数说明请参考 `clude --help` 或 [CLI 模块文档](src/clude_code/cli/README.md)。

### 3.1 `clude chat` (核心入口)

- **交互模式**:
  - `clude chat`：基础对话。
  - `clude chat --live --live-ui opencode`：**推荐**，多窗格 TUI 体验。
  - `clude chat --live --live-ui enhanced`：Claude Code 风格侧边栏 UI。

- **非交互模式**:
  - `clude chat -p "审查代码"`：单次执行并退出。
  - `clude chat -p --output-format json "..."`：适合脚本集成。

- **会话管理**:
  - `clude chat -c`：继续上一次会话。
  - `clude chat -r <session_id>`：恢复指定会话。

### 3.2 辅助命令

- `clude tools`：查看可用工具清单（支持 `--json`）。
- `clude doctor`：环境诊断与修复。
- `clude models`：列出可用模型。

---

## 4. 文档导航 (Documentation Index)

本项目文档体系分为设计规范、进度报告与技术深挖三部分。

### 4.1 核心索引
- **[项目总览 (Overview)](./docs/00-overview.md)**：包含完整的功能矩阵与技术文档索引。
- **[开发计划 (Roadmap)](./docs/16-development-plan.md)**：包含最新的 P0/P1/P2 迭代计划与审计结论。
- **[模块进度 (Progress)](./src/README.md)**：技术实现的详细计分卡与业界对比。

### 4.2 深度技术报告 (`docs/technical-reports/`)
- **[业界 Code Agent 技术白皮书](./docs/technical-reports/industry-whitepaper.md)**：架构原理与最佳实践。
- **[Agent 决策链路审计与评分](./docs/17-agent-decision-audit.md)**：深度剖析 Trace ID、控制协议与重规划机制。
- **[RAG 深度调优路线图](./docs/technical-reports/rag-tuning.md)**：Hybrid Search 与 AST Chunking 实现细节。
- **[健壮性复盘报告](./docs/technical-reports/robustness-review.md)**：系统稳定性分析。

---

## 5. 实现流程图

![Core Implementation Flow](src/assets/core_implementation_flow.svg)

*(注：动画展示了从 CLI 输入到 Agent 编排再到 LLM 反馈的完整闭环)*
