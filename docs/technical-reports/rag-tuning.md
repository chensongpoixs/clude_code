# RAG 索引深度调优路线图 (RAG Deep Tuning Roadmap)

> **Status (状态)**: Active Optimization (持续优化中)  
> **Focus (目标)**: Precision & Stability (精度与稳定性)

## 1. 核心问题定义 (Problem Definition)

RAG 在 Code Agent 里的“索引深度调优”，本质上是在三者之间做工程平衡：

- **召回质量 (Recall Quality)**：能否在需要时找到“正确且足够小”的代码片段 (Precision + Recall)。
- **吞吐与延迟 (Throughput & Latency)**：索引是否拖慢交互 (后台索引要稳、查询要快)。
- **工程稳定性 (Engineering Stability)**：增量更新是否可靠、是否可恢复、是否可观测。

业界 (Cursor/Claude Code/Aider) 普遍采用 **混合上下文路线 (Hybrid Context)**：

1. **Repo Map / 结构化概览**：快速让模型知道“项目有什么、入口在哪”。
2. **符号级检索 (Symbol/LSP)**：解决“跳转/引用/定义”类问题。
3. **向量检索 (Vector Search)**：解决“语义描述找代码”类问题。
4. **文本检索 (Text Search/rg)**：解决“我知道关键词/字符串”类问题。

> **结论**: 最优路线不是单一 Vector RAG，而是 **Repo Map + (LSP/ctags) + rg + Vector** 的组合。

---

## 2. 业界最佳实现路线 (Best Practices)

### 2.1 索引管线 (Indexing Pipeline)

业界“最佳实践”通常具备以下特征：

- **增量索引 (Incremental Indexing)**：使用 File Watcher (inotify/FSEvents) 或 mtime+hash。
- **状态持久化 (State Persistence)**：索引状态写入磁盘 (Manifest)，重启可恢复。
- **护栏 (Guardrails)**：跳过二进制/超大文件/依赖目录；失败降级。
- **语义分块 (Semantic Chunking)**：优先 **AST-aware (Tree-sitter)**；退化到启发式 (Heuristic)。
- **批处理与节流 (Batching & Throttling)**：Embedding Batch、最大并发控制。
- **可观测 (Observability)**：索引进度、失败原因、吞吐指标。

### 2.2 查询管线 (Query Pipeline)

业界在查询侧通常做三段式：

1. **Query Rewrite (查询重写)**：将“用户描述”改写成更可检索的 Query。
2. **Hybrid Retrieve (混合检索)**：
   - 先用 `rg` 做“强过滤”或补充信号。
   - 再做向量检索取 Top-K。
   - 结合 Repo Map / 符号信息做 **Rerank (重排序)** (基于 Symbol/Scope/Node Type 等元数据)。
3. **Context Packing (上下文打包)**：
   - 只回喂关键片段 + 引用 (路径/行号)。
   - 控制 Token：截断、去重、按重要性排序。

---

## 3. 本项目现状与计划 (Status & Plan)

### 3.1 已补齐能力 (Implemented)

- **接口一致性**: `VectorStore.search()` 统一接收向量，`semantic_search()` 负责 Embedding。
- **增量索引可恢复**: `IndexerService` 引入磁盘状态文件 `.clude/index_state.json`。
- **护栏机制**: 跳过超大文件 (`rag.max_file_bytes`) 和二进制文件。
- **AST-aware 分块**: 引入 `TreeSitterChunker`，支持 `symbol`/`node_type`/`scope` 元数据。
- **基础 Rerank**: 基于 Metadata 的加权打分 (Symbol Hit, Scope Match)。

### 3.2 下一步计划 (Next Steps)

- [ ] **更强的变更检测**: 引入 "mtime + hash + size" 组合，解决文件系统抖动问题。
- [ ] **并发索引 (Concurrent Indexing)**: 使用线程池控制并发。
- [ ] **查询侧 Hybrid**: 将 `rg` 结果正式作为 Rerank 信号。
- [ ] **向量库治理**: Schema 迁移与多模型支持。

---

## 4. 结论 (Conclusion)

对本项目 (CLI、Local-First) 而言，最佳实现路线是：

> **Hybrid RAG = Repo Map + AST-aware Indexing + Incremental Recovery + Rerank（仓库映射+语法树索引+增量可恢复+重排序）**  
> 注释：Repo Map=仓库映射，AST-aware Indexing=语法树感知索引，Incremental Recovery=增量可恢复，Rerank=重排序

一句话结论：**“增量可恢复索引 + 护栏 + 批处理 + AST-aware 分块”** 是当前最符合业界与本项目约束的最佳路线。
