## repo_map（`src/clude_code/tooling/tools/repo_map.py`）业界优化点

### 当前模块职责

- 通过 `ctags` 生成仓库符号概览（“Repo Map”），并做权重筛选（Top N 文件、Top N 符号）以控制上下文体积。

### 业界技术原理

- **Top-K summarization**：仓库图谱本质是“检索前置摘要”，必须强制 Top-K，避免 system prompt 被 repo_map 挤爆。
- **结构优先**：用“目录/文件/符号”树结构，比把所有符号扁平输出更利于模型理解架构。
- **可选依赖降级**：ctags 不存在时应优雅降级（返回提示而不是崩溃）。

### 现状评估（本项目）

- 已实现：ctags 缺失降级；排除常见目录；按文件深度与符号数做权重；Top 50 文件、单文件最多 8 符号。

### 可优化点（建议优先级）

- **P0：与 system prompt 的 token 预算联动**
  - **原理**：repo_map 的长度需要动态适配模型窗口与当前上下文占用。
  - **建议**：在 orchestrator 构建 system prompt 时，对 repo_map 做“按 token 预算截断”（你们已有类似策略，建议保持单点）。

- **P1：增量更新（incremental）**
  - **原理**：每轮都全量跑 ctags 成本高。
  - **建议**：以 git diff 或 mtime 为依据做增量；或缓存 repo_map 并定期刷新。


