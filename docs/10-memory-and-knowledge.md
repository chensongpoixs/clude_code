# 10 | 记忆与知识库（可实现规格）(Memory & Knowledge Spec)

> **Status (状态)**: Active Development (持续开发中)  
> **Audience (读者)**: Maintainers / Memory System Engineers (维护者/记忆系统工程师)  
> **Goal (目标)**: 定义 Agent 如何在不泄露隐私的前提下，记住“用户偏好、仓库约定、长期上下文”，实现跨会话的记忆（Memory/记忆）与知识管理（Knowledge/知识）。

---

## 1. 记忆分层 (Memory Hierarchy)

### 1.1 短期记忆 (Session Memory)
- **范围**: 当前会话/当前任务。
- **形态**:
  - 原始对话 (Chat History)。
  - 会话摘要 (Session Summary)。
  - 结构化工具调用 (Tool Call Summaries)。
- **实现**: 内存 + `SessionStore` (JSON 文件)。

### 1.2 中期记忆 (Project/Workspace Memory)
- **范围**: 特定仓库/项目。
- **核心载体**: `CLUDE.md` (Project Memory/项目记忆)。
  - **定位**: 项目级的“长期上下文”与“协作规则”。
  - **内容**: 构建命令、架构约定、关键模块路径、技术决策记录。
  - **注入**: 每次启动自动读取并注入 System Prompt。
- **实现**: 本地文件 `CLUDE.md` (Markdown)。

### 1.3 长期记忆 (User/Global Memory)
- **范围**: 用户偏好与组织规范（跨仓库）。
- **示例**: 输出语言偏好、安全策略偏好。
- **实现**: `~/.clude/config.yaml` 或全局记忆库。

---

## 2. 项目记忆：`CLUDE.md` (Project Memory)

> **当前实现 (Current Implementation)**: 已落地。

### 2.1 规范与格式
`CLUDE.md` 位于项目根目录，是 Agent 的“外挂大脑”。

```markdown
# CLUDE.md

## Project Context
这是一个基于 Python 的 CLI 工具...

## Commands
- Build: `python -m build`
- Test: `pytest tests/`

## Conventions
- 使用 Type Hints
- 优先使用 `pathlib` 而非 `os.path`
```

### 2.2 自动加载机制
- **Orchestrator** 初始化时，检测 `CLUDE.md`。
- 若存在，读取内容并附加到 `SYSTEM_PROMPT` 的 "Project Context" 区域。
- UI 层（Enhanced/OpenCode TUI）在启动时显示“项目记忆已加载”。

---

## 3. RAG 知识库 (Knowledge Base)

> **当前实现 (Current Implementation)**: RAG 深度调优中 (Docs 03)。

- **向量检索 (Vector Search)**: 解决“语义找代码”问题。
- **符号索引 (Symbol Index)**: 解决“定义/引用跳转”问题。
- **AST 分块 (AST Chunking)**: 提升代码片段的语义完整性。

---

## 4. 记忆写入与治理 (Memory Write & Governance)

### 4.1 写入策略
- **显式写入**: 用户通过 `/memory` 命令更新 `CLUDE.md`。
- **自动推断 (Roadmap)**: Agent 识别到稳定的构建命令失败模式后，建议用户更新记忆。

### 4.2 安全与隐私
- **敏感信息过滤**: 禁止将 Key/Token 写入 `CLUDE.md`。
- **审计**: 记忆的修改通过 `update_memory` (或文件编辑) 工具进行，有完整 Audit Log。

---

## 5. 相关文档 (See Also)

- **仓库索引与检索 (Repo Indexing)**: [`docs/03-repo-indexing.md`](./03-repo-indexing.md)
- **上下文与提示词 (Context Spec)**: [`docs/04-context-and-prompting.md`](./04-context-and-prompting.md)
- **RAG 深度调优 (Technical Report)**: [`docs/technical-reports/rag-tuning.md`](./technical-reports/rag-tuning.md)
