## 回喂压缩层（`src/clude_code/tooling/feedback.py`）业界优化点

### 当前模块职责

- 将各工具返回的 `ToolResult` **压缩为“决策关键信号”**，再喂回 LLM，避免上下文被工具输出挤爆。

### 业界技术原理

- **Bounded output（硬上限）**：工具输出必须有字符/行数/条目硬上限，否则会导致上下文挤压、循环与失忆。
- **结构化摘要优先**：比起拼接大文本，返回结构化摘要（counts/paths/offsets/preview）更利于模型做下一步决策。
- **引用优先（reference over content）**：尽量回喂“路径+行号范围+少量预览”，让模型按需再读。
- **Query-aware sampling**：read_file/grep 等按关键词做窗口采样，比“纯 head/tail”更省 token 且更贴近任务。

### 现状评估（本项目）

- 已对 `list_dir/grep/read_file/glob_file_search/run_cmd/apply_patch/undo_patch/search_semantic/websearch/webfetch/codesearch/write_file` 做摘要回喂。
- `read_file` 已实现关键词窗口采样 + head/tail fallback + 上限截断。

### 进一步可优化点

- **P0：统一“摘要预算”策略**
  - **原理**：不同阶段（planning/execute/diagnose）对细节需求不同；同一压缩强度容易“要么不够细、要么太啰嗦”。  
  - **建议**：引入 `compression_level`（minimal/balanced/aggressive），并由 orchestrator 根据 token 利用率动态切换。

- **P1：run_cmd 的回喂与工具输出保持一致**
  - **原理**：工具输出与回喂摘要不一致会误导模型（例如工具头尾截断，回喂只给尾部）。  
  - **建议**：feedback 层与 `run_cmd` 的头尾策略统一（或直接复用同一截断函数）。

- **P1：稳定字段集（compat contract）**
  - **原理**：UI/日志/提示词会依赖字段名，字段漂移会造成“系统性脆弱”。  
  - **建议**：为每类工具固定输出字段集（如 grep 固定 `engine/hits_total/hits_shown/truncated`）。

- **P2：可恢复定位（source anchors）**
  - **原理**：业界会把定位信息（file+line+hash）作为后续编辑/回滚依据。  
  - **建议**：read_file 回喂可增加 `sha256_prefix`；grep 命中可增加 `match_id=path:line:col`。

{
  "cells": [],
  "metadata": {
    "language_info": {
      "name": "python"
    }
  },
  "nbformat": 4,
  "nbformat_minor": 2
}