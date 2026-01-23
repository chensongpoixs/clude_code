## apply_patch / undo_patch（`src/clude_code/tooling/tools/patching.py`）业界优化点

### 当前模块职责

- **apply_patch**：在文件中进行块替换（精确匹配为主，支持模糊匹配/上下文匹配），并生成可回滚的 undo 记录。
- **undo_patch**：基于 `.clude/undo/{undo_id}.json` 与备份文件恢复，并默认做 hash 冲突检测。

### 业界技术原理

- **Patch-first editing**：编辑应以“可验证 diff”为核心，降低模型误编辑概率。
- **可回滚（reversible）**：写操作必须能回滚，且回滚应做冲突检测（避免覆盖用户后续改动）。
- **Impact analysis**：对编辑影响做结构化分析（哪些区块改了、是否可能破坏语法/测试）。

### 现状评估（本项目）

- 已实现：before/after hash、undo_id、冲突检测（force 可覆盖）、增强 patch engine（validate/diff/impact）。
- 回喂层已只保留高信号字段（hash/undo_id/匹配信息）。

### 可优化点（建议优先级）

- **P1：更强的“编辑前验证”与“编辑后验证”**
  - **原理**：patch 成功 ≠ 代码可用；业界会引入轻量校验（lint/compile）作为策略的一部分。
  - **建议**：在 risk_router/tool_lifecycle 上增加“写后可选验证步骤”（例如 python compileall 针对修改文件）。

- **P2：Undo 元数据索引**
  - **原理**：随着 undo 文件增多，需要可检索与清理策略。
  - **建议**：提供 `clude undo list/clean`，按时间与路径聚合。


