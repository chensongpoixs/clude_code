# clude-code: 业界级本地编程代理 (Code Agent CLI)

**clude-code** 是一个受 Claude Code 启发、专注于本地化落地的编程代理 CLI。它通过一套闭环的 Agent 编排逻辑，使本地模型（通过 `llama.cpp`）能够理解代码库、规划任务、执行高精度补丁编辑、并进行审计追溯。

本仓库沉淀了从**功能分析**、**架构设计**到**模块化实现**的全过程文档与源码。



[业界 Code Agent 技术原理深度白皮书 (Technical Whitepaper)](/src/INDUSTRY_CODE_AGENT_TECH_WHITEPAPER.md)



## 1. 核心特性 (Key Features)

| 特性 | 说明 | 状态 |
| :--- | :--- | :--- |
| **本地优先 (Local-First)** | 深度集成 `llama.cpp` HTTP API，保护隐私，无须云端 Token。 | ✅ 已落地 |
| **精准编辑 (Patch Engine)** | 借鉴 Aider 的 `Search-Replace` 块逻辑，支持 `apply_patch` 与 `undo_patch`。 | ✅ 已落地 |
| **仓库感知 (Repo Map)** | 基于 `universal-ctags` 的符号拓扑，让 Agent 拥有全局架构视野。 | ✅ 已落地 |
| **语义 RAG (Vector Search)** | 集成 `LanceDB` + `fastembed`，支持对大规模代码库的异步索引与语义检索。 | ✅ 已落地 |
| **安全审计 (Audit Trace)** | 全量记录工具调用日志与执行轨迹，支持 Hash 级补丁完整性校验。 | ✅ 已落地 |
| **交互式修复 (Auto-Fix)** | `doctor --fix` 能够自动诊断并跨平台安装 `rg`、`ctags` 等外部依赖。 | ✅ 已落地 |

---

## 2. 快速开始 (Quick Start)

### 2.1 环境准备 (PowerShell / Windows)

```powershell
# 1. 创建环境
conda create -n clude_code python=3.11 -y
conda activate clude_code

# 2. 安装项目（含开发模式）
pip install -e .
pip install lancedb fastembed watchdog

# 3. 配置 LLM 访问（确保 llama.cpp server 已启动）
$env:CLUDE_WORKSPACE_ROOT="D:\Work\AI\clude_code"
$env:CLUDE_LLM__BASE_URL="http://127.0.0.1:8899"
$env:CLUDE_LLM__API_MODE="openai_compat"
```

### 2.2 启动对话

```powershell
# 诊断环境与缺失工具
clude doctor --fix

# 进入交互式开发对话
clude chat --debug
```

---

## 3. CLI 命令参考（参数说明）

> 参数以 `src/clude_code/cli/main.py` 为准；工具清单以 `ToolSpec` 注册表为准（`clude tools` 可直接打印）。

### 3.1 `clude chat`
- **用途**：进入交互式 Agent 会话（读/搜/改/跑命令/验证闭环）。
- **常用参数**
  - **`--model TEXT`**：指定 llama.cpp 的 model id
  - **`--select-model`**：从 `/v1/models` 交互选择模型（openai_compat）
  - **`--debug`**：输出可观测轨迹，并写入 `.clude/logs/trace.jsonl`
  - **`--live`**：固定 50 行实时刷新 UI（开启后自动启用 `--debug`，结束后保持最终状态）

```bash
clude chat
clude chat --debug
clude chat --live
clude chat --model "ggml-org/gemma-3-12b-it-GGUF"
```

### 3.2 `clude tools`
- **用途**：输出可用工具清单（同源 ToolSpec），用于排障/文档/脚本。
- **参数**
  - **`--schema`**：附带 JSON Schema
  - **`--json`**：JSON 输出
  - **`--all`**：包含内部/不可调用项（诊断用）

```bash
clude tools
clude tools --json
clude tools --json --schema
```

### 3.3 `clude doctor`
- **用途**：诊断外部依赖（rg/ctags 等）、工作区读写、llama.cpp 连通性。
- **参数**
  - **`--fix`**：尝试自动安装/修复缺失依赖（会交互确认）

```bash
clude doctor
clude doctor --fix
```

### 3.4 `clude models`
- **用途**：列出 `/v1/models`（openai_compat）返回的模型 id。

```bash
clude models
```

### 3.5 `clude version`

```bash
clude version
```

---

## 3. 实现流程图 (Implementation Architecture)

![Core Implementation Flow](src/assets/core_implementation_flow.svg)

*(注：动画展示了从 CLI 输入到 Agent 编排再到 LLM 反馈的完整闭环，SVG 源码位于 `src/assets/core_implementation_flow.svg`)*

---

## 4. 文档导航 (Documentation Index)

本项目文档分为两个维度：**设计规范 (docs/)** 与 **实现分析 (src/)**。

### 4.1 核心设计规范 (`docs/`)
- [00 | 项目总览](./docs/00-overview.md)：产品目标、非目标与安全边界。
- [01 | 流程与状态机](./docs/01-e2e-flow-and-state-machine.md)：Agent 运行逻辑。
- [02 | 工具协议](./docs/02-tool-protocol.md)：JSON Schema 定义与沙箱策略。
- [06 | 代码编辑](./docs/06-code-editing-and-patching.md)：补丁引擎详细规范。

### 4.2 落地进度报告 (`src/`)
- [📊 模块进度总览](./src/README.md)：包含完成度百分比、下一步规划。
- [📄 业界对比白皮书](./src/INDUSTRY_CODE_AGENT_TECH_WHITEPAPER.md)：深度技术拆解与 SVG 流程演示。
- [🔍 RAG 实现方案](./src/IMPLEMENTATION_ANALYSIS_LANCEDB_INDEXING.md)：LanceDB 后台异步索引逻辑。
- [🛠️ 精准补丁分析](./src/IMPLEMENTATION_ANALYSIS_PATCH_UNDO.md)：`apply_patch` 与 `undo` 的实现细节。

---

## 5. 许可证与致谢

本研究与开发过程借鉴了 `Aider`, `Claude Code` 与 `Cursor` 的优秀工程实践。
