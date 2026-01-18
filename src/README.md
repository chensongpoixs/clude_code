# 💻 Clude Code Developer Portal

> **Internal Developer Documentation (内部开发者文档)**  
> Source Code Analysis, Module Status, and Implementation Details. (源码分析、模块状态与实现细节)

---

## 1. 模块全景图 (Module Panorama)

| Module | Directory | Role | Completeness |
| :--- | :--- | :--- | :--- |
| **🚀 CLI** | `src/clude_code/cli` | Entry Point, TUI, Interaction | █████████░ 95% |
| **⚙️ Orchestrator** | `src/clude_code/orchestrator` | State Machine, Planning | █████████░ 90% |
| **🛠️ Tooling** | `src/clude_code/tooling` | File IO, Shell, Patching | █████████░ 92% |
| **🧠 Knowledge** | `src/clude_code/knowledge` | RAG, Vector Store, Indexing | ████████░░ 85% |
| **📡 LLM** | `src/clude_code/llm` | Client, Tokenizer | ████████░░ 85% |
| **🛡️ Policy** | `src/clude_code/policy` | Security, Permission | █████████░ 90% |
| **🔌 Plugins** | `src/clude_code/plugins` | Extensions, UI Plugins | ████████░░ 88% |

---

## 2. 关键技术白皮书 (Technical Whitepapers)

我们鼓励开发者先阅读以下核心文档，理解设计哲学：

*   **[Agent 决策链路审计报告](../docs/17-agent-decision-audit.md)**: 理解 Trace ID、Protocol 和 Re-planning 的设计权衡。
*   **[业界 Code Agent 架构对比](../docs/technical-reports/industry-whitepaper.md)**: 为什么我们选择 Local-First 和 AST RAG。
*   **[RAG 深度调优指南](../docs/technical-reports/rag-tuning.md)**: 向量检索与混合搜索的实现细节。

---

## 3. 核心机制详解 (Core Mechanisms)

### 3.1 本地优先 (Local-First)
我们不依赖云端 API。所有逻辑通过 `llama.cpp` 的 HTTP 接口完成。
*   **Endpoint (接口地址)**: `http://127.0.0.1:8899/v1/chat/completions` (OpenAI Compat / OpenAI 兼容)
*   **Token Counting (Token 估算)**: 本地估算，用于 Budget Control (预算控制)。

### 3.2 工具契约 (ToolSpec)
`ToolSpec` 是单一真实源。
1.  **Definition (定义)**: 在 `tool_dispatch.py` 中定义 Schema (模式/契约)。
2.  **Validation (校验)**: 运行时通过 `Pydantic` 强校验。
3.  **Generation (生成)**: 自动生成 System Prompt (系统提示词) 和 `clude tools` 文档。

### 3.3 可观测性 (Observability)
*   **Trace ID**: 贯穿全链路的 UUID。
*   **Audit Log (审计日志)**: `~/.clude/audit.jsonl` 记录每一次工具调用。
*   **Live UI (实时界面)**: 通过 Event Stream (事件流) 实时驱动 TUI 更新。

---

## 4. 开发指南 (Contribution Guide)

### 环境搭建
```bash
pip install -e ".[dev,rag,ui]"
```

### 运行测试
```bash
pytest src/clude_code/tests/
```

### 代码规范
*   遵循 PEP 8。
*   所有新功能必须有对应的 `ToolSpec` 和文档更新。
*   关键路径（Orchestrator）必须有详细的 Logging。

---
