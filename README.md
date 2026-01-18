# Clude Code: 业界级本地编程代理 (Industry-Grade Local Code Agent)

> **Status (状态)**: Active Development (持续开发中)  
> **Inspired by (灵感来源)**: Claude Code & Aider

**Clude Code** 是一个专注于**本地化落地 (Local-First)** 的编程代理 CLI。它通过一套闭环的 **Agent 编排逻辑 (Orchestration)**，使本地模型 (通过 `llama.cpp`) 能够理解代码库、规划任务、执行高精度补丁编辑、并进行审计追溯。

本仓库沉淀了从**功能分析**、**架构设计**到**模块化实现**的全过程文档与源码。

> 📖 **[技术白皮书与模块进度总览 (Technical Overview)](./src/README.md)** (开发者必读)

---

## 1. 核心特性 (Key Features)

| 特性 | 说明 | 状态 |
| :--- | :--- | :--- |
| **本地优先 (Local-First)** | 深度集成 `llama.cpp` HTTP API，保护隐私，无须云端 Token。 | ✅ Ready |
| **精准编辑 (Patch Engine)** | 借鉴 Aider 的 **Search-Replace** 块逻辑，支持 `apply_patch` 与 `undo_patch`。 | ✅ Ready |
| **仓库感知 (Repo Map)** | 基于 `universal-ctags` 的符号拓扑，让 Agent 拥有全局架构视野。 | ✅ Ready |
| **语义 RAG (Vector Search)** | 集成 `LanceDB` + `fastembed`，支持 **AST 分块** 与 **混合检索 (Hybrid Search)**。 | ✅ Ready |
| **交互体验 (TUI)** | 支持 **OpenCode 风格 TUI** (多窗格滚动) 和 **Claude Code 风格 CLI**。 | ✅ Ready |
| **安全审计 (Audit Trace)** | 全量记录工具调用日志与执行轨迹，支持 Hash 级补丁完整性校验。 | ✅ Ready |
| **交互式修复 (Auto-Fix)** | `doctor --fix` 能够自动诊断并跨平台安装 `rg`、`ctags` 等外部依赖。 | ✅ Ready |

---

## 2. 快速开始 (Quick Start)

### 2.1 环境准备 (Prerequisites)

```powershell
# 1. 创建环境 (Create Environment)
conda create -n clude_code python=3.11 -y
conda activate clude_code

# 2. 安装项目 (Install Package)
pip install -e ".[rag]"

# 3. 配置 LLM (Configure LLM)
$env:CLUDE_WORKSPACE_ROOT="D:\Work\AI\clude_code"
$env:CLUDE_LLM__BASE_URL="http://127.0.0.1:8899"
$env:CLUDE_LLM__API_MODE="openai_compat"
```

### 2.2 启动对话 (Start Chat)

```powershell
# 1. 诊断环境 (Doctor)
clude doctor --fix

# 2. 初始化项目记忆 (Init Memory)
clude chat --select-model
/init

# 3. 启动 TUI (Start TUI)
clude chat --live --live-ui opencode
```

---

## 3. CLI 命令参考 (Command Reference)

> 完整参数说明请参考 `clude --help`。

### 3.1 `clude chat` (核心入口)

- **交互模式 (Interactive)**:
  - `clude chat --live --live-ui opencode`: **推荐**，多窗格 TUI。
  - `clude chat --live --live-ui enhanced`: Claude Code 风格侧边栏。

- **非交互模式 (Non-Interactive)**:
  - `clude chat -p "Review code"`: 单次执行 (Print Mode)。
  - `clude chat -p --output-format json "..."`: 脚本集成模式。

- **会话管理 (Session Management)**:
  - `clude chat -c`: 继续上一次会话 (Continue)。
  - `clude chat -r <session_id>`: 恢复指定会话 (Resume)。

### 3.2 辅助命令 (Utility Commands)

- `clude tools`: 查看可用工具清单 (Tools List)。
- `clude doctor`: 环境诊断与修复 (Environment Check)。
- `clude models`: 列出可用模型 (Models List)。

---

## 4. 文档导航 (Documentation Index)

本项目文档体系分为设计规范、进度报告与技术深挖三部分。

### 4.1 核心索引 (Core Index)
- **[项目总览 (Overview)](./docs/00-overview.md)**: 完整的功能矩阵与架构图。
- **[开发计划 (Roadmap)](./docs/16-development-plan.md)**: P0/P1/P2 迭代计划与审计结论。
- **[模块进度 (Progress)](./src/README.md)**: 技术实现的计分卡与业界对比。

### 4.2 深度技术报告 (Deep Dive Reports)
- **[业界 Code Agent 技术白皮书](./docs/technical-reports/industry-whitepaper.md)**: 架构原理与最佳实践。
- **[Agent 决策链路审计与评分](./docs/17-agent-decision-audit.md)**: Trace ID、控制协议与重规划机制。
- **[RAG 深度调优路线图](./docs/technical-reports/rag-tuning.md)**: Hybrid Search 与 AST Chunking。
- **[健壮性复盘报告](./docs/technical-reports/robustness-review.md)**: 系统稳定性分析。

---

## 5. 实现流程图 (Implementation Flow)

![Core Implementation Flow](src/assets/core_implementation_flow.svg)

*(注：动画展示了从 CLI 输入到 Agent 编排再到 LLM 反馈的完整闭环)*
