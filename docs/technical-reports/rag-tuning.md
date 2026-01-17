# RAG 索引深度调优：业界最佳技术路线分析与本项目落地结论

## 1. 你要解决的本质问题是什么？

RAG 在 Code Agent 里的“索引深度调优”，本质上是在三者之间做工程平衡：

- **召回质量**：能否在需要时找到“正确且足够小”的代码片段（高 precision + 高 recall）。
- **吞吐与延迟**：索引是否拖慢交互（后台索引要稳、查询要快）。
- **工程稳定性**：增量更新是否可靠、是否可恢复、是否可观测、是否不会污染上下文窗口。

业界（Cursor/Claude Code/Aider + 企业内部 RAG）普遍采用 **混合上下文路线**：

- **Repo Map / 结构化概览**：快速让模型知道“项目有什么、入口在哪”（低成本高收益）。
- **符号级检索（LSP/ctags）**：解决“跳转/引用/定义”类问题（高精度）。
- **向量检索（Embedding + Vector DB）**：解决“语义描述找代码”类问题（跨语言、跨命名更强）。
- **文本检索（rg/grep）**：解决“我知道关键词/字符串”类问题（最稳定、成本最低）。

结论：**最优路线不是单一 Vector RAG，而是 Repo Map + (LSP/ctags) + rg + Vector 的组合。**

---

## 2. 业界最佳实现路线（推荐）

### 2.1 索引管线（Indexing Pipeline）

业界“最佳实践”通常具备以下特征：

- **增量索引（必选）**：使用 file watcher（inotify/FSEvents/ReadDirectoryChangesW）或 mtime+hash；
- **状态持久化（必选）**：索引状态写入磁盘（manifest），重启可恢复；
- **护栏（必选）**：跳过二进制/超大文件/依赖目录；失败降级；
- **语义分块（强烈推荐）**：优先 AST-aware（Tree-sitter/LSP）；退化到启发式（def/class/空行）；
- **批处理与节流（必选）**：embedding batch、最大并发控制、backpressure；
- **可观测（推荐）**：索引进度、失败原因、吞吐指标、向量库大小、缓存命中率。

### 2.2 查询管线（Query Pipeline）

业界在查询侧通常做三段式：

1. **Query Rewrite/Normalize**：将“用户描述”改写成更可检索的 query（可选）。
2. **Hybrid Retrieve**：
   - 先用 rg 做“强过滤”或补充信号；
   - 再做向量检索取 top-k；
   - 结合 Repo Map / 符号信息做 rerank（推荐：symbol/scope/node_type 等元数据 + 轻量词法信号）。
3. **Context Packing**：
   - 只回喂关键片段 + 引用（路径/行号）；
   - 控制 token：截断、去重、按重要性排序。

---

## 3. 本项目当前实现与“最佳路线”的差距（已补齐/仍需补齐）

### 3.1 已补齐（本次改动）

- **接口一致性**：
  - `VectorStore.search()` 统一为 **接收向量**；
  - `semantic_search()` 负责 embedding，`VectorStore` 只负责存取与向量检索（更贴近业界分层）。
- **增量索引可恢复**：
  - `IndexerService` 引入磁盘状态文件：`.clude/index_state.json`；
  - 重启后可以基于状态继续增量索引。
- **护栏**：
  - 跳过超大文件（`rag.max_file_bytes`）；
  - 跳过二进制文件（NUL byte 启发式）；
  - embedding 采用 batch（`rag.embed_batch_size`）避免内存尖峰。
- **配置落地**：
  - `rag.scan_interval_s / max_file_bytes / embed_batch_size / chunk_*` 等参数进入全局配置。

### 3.2 仍建议补齐（下一阶段）

- ✅ **AST-aware 语义分块（Tree-sitter）**：已引入可选 `tree_sitter` 分块器（缺依赖自动降级到启发式），并将 `symbol/node_type/scope/language/chunk_id` 元数据写入向量库；
- ✅ **查询侧 rerank（业界推荐）**：语义检索返回包含 `score/_distance`，并基于 `symbol/scope/node_type/path/词法命中` 做轻量 rerank，提升 precision 与可解释性；
- <span style="color:red">**更强的“变更检测”**</span>：mtime 在 Windows/网络盘上可能抖动，建议“mtime + hash + size”组合；
- **并发索引**：使用线程池/进程池并控制并发与队列长度；
- **向量库 schema 与维度治理**：embedding_model 变化时的迁移策略（单库多表或按模型版本分表）；
- **查询侧 hybrid**：将 `rg` 的结果作为 rerank 或过滤信号（提升 precision）。

---

## 4. 结论：什么是“最佳实现”？

对本项目（纯 CLI、本地 llama.cpp、可离线）的约束来说，**最佳实现路线**是：

1. **Repo Map（已完成）**：结构化概览 + 核心文件排序；
2. **Hybrid 检索（建议持续强化）**：
   - 关键词 → `rg`；
   - 语义描述 → Vector；
   - 结构跳转 → LSP（或 ctags）；
3. **可恢复的增量索引（已完成骨架）**：
   - 状态持久化 + 护栏 + 批处理；
4. **AST-aware 分块（下一阶段最重要的质量杠杆）**：
   - 没有 AST-aware，向量召回上限会明显受限（尤其跨文件复杂任务）。

一句话结论：**“增量可恢复索引 + 护栏 + 批处理 +（下一步 AST-aware 分块）”是当前最符合业界与本项目约束的最佳路线。**


