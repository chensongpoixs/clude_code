# 03 | 仓库索引与检索（可实现规格）(Repo Indexing & Retrieval Spec)

> **Status (状态)**: Stable Spec (稳定规格，可直接落地实现)  
> **Audience (读者)**: Maintainers / RAG Engineers (维护者/RAG 工程师)  
> **Goal (目标)**: 在“超大仓库/多语言/多构建系统”下，仍能在秒级定位相关代码，并为上下文构建（Context Builder/上下文构建器）提供高质量候选片段。

---

## 1. 子模块拆分 (Subsystems)

### 1.1 文件树与元数据（File Catalog/文件目录）
- **职责**：列出 workspace 下文件、大小、修改时间、是否二进制、语言推断
- **输入**：workspace 路径、ignore 规则（.gitignore/.cursorignore/自定义）
- **输出**：`FileEntry[]`
- **实现要点**：
  - 增量更新：基于 mtime/哈希
  - 忽略规则合并：gitignore + 产品 ignore
  - 大文件与二进制文件识别（阈值可配置）

### 1.2 精确搜索（Grep/Ripgrep Adapter/精确检索适配器）
- **职责**：高性能文本搜索（regex、大小写、glob）
- **输入**：pattern、path scope、glob、head_limit
- **输出**：`SearchHit[]`（文件、行号、上下文）
- **实现要点**：
  - 封装 `rg` 或内置搜索；输出统一结构
  - 结果裁剪：按文件/总行数上限

### 1.3 语义检索（Semantic Search/语义检索，可选）
- **职责**：基于 embedding 的语义相似度召回
- **输入**：query、目录 scope、top_k
- **输出**：`SemanticHit[]`（chunk_id、score、文件/行范围）
- **实现要点**：
  - chunk 策略：AST-aware 分块（优先）→ 启发式分块
  - 向量库：LanceDB (本地嵌入式)
  - 异步索引构建：首次缺索引时降级到 grep

### 1.4 符号索引（Symbol Index/符号索引，可选）
- **职责**：定义/引用、跳转、调用链
- **实现**：目前通过 Tree-sitter 在分块时提取符号元数据（Symbol Metadata）。

---

## 2. 数据结构（建议）(Data Structures)

### 2.1 FileEntry（文件条目）
- `path: string`
- `size_bytes: number`
- `mtime_ms: number`
- `is_binary: boolean`
- `language?: string`

### 2.2 SearchHit（grep 命中）
- `path: string`
- `line: number`
- `column?: number`
- `preview: string`
- `before?: string[]`
- `after?: string[]`

### 2.3 CodeChunk（语义索引用 / Semantic Chunk）
> **当前实现**: `src/clude_code/knowledge/chunking.py`

- `chunk_id: string`
- `path: string`
- `start_line: number`
- `end_line: number`
- `content_hash: string`
- `tokens_estimate?: number`
- **Metadata (元数据)**:
  - `language`: 编程语言 (e.g., "python", "typescript")
  - `symbol`: 包含的符号名 (e.g., "AgentLoop", "run_turn")
  - `node_type`: AST 节点类型 (e.g., "class_definition", "function_definition")
  - `scope`: 父作用域路径 (e.g., "src/clude_code/orchestrator")

---

## 3. 检索策略与重排序 (Retrieval & Reranking)

> **当前实现**: `src/clude_code/orchestrator/agent_loop/semantic_search.py`

### 3.1 混合检索 (Hybrid Search)
- **Vector Search**: 使用 `lancedb` 检索 Top-K (K=50)。
- **Metadata Filtering**: 按 `scope` 过滤。

### 3.2 重排序 (Reranking / Scoring)
对初步召回的 Chunk 进行二次打分：
1.  **Base Score**: 向量相似度 (Cosine Similarity)。
2.  **Boosts (加权)**:
    - `symbol` 匹配查询词: +0.2
    - `path` 匹配查询词: +0.1
    - `scope` 匹配当前上下文: +0.1
3.  **Penalties (惩罚)**:
    - 这里的惩罚逻辑（如过长 Chunk）可配置。
4.  **Final Sort**: 按最终 Score 排序，取 Top-N 返回给 Agent。

---

## 4. 索引生命周期 (Index Lifecycle)

### 4.1 构建触发 (Triggers)
- 首次打开 workspace (自动后台启动)。
- 用户显式命令 `/index build` (Todo)。
- 文件系统变更（watcher）触发增量更新。

### 4.2 存储位置 (Storage)
- `.clude/vector_db/` (LanceDB Table)

### 4.3 失效策略 (Invalidation)
- 文件 content_hash 变化 → 对应 chunk 失效重建。

---

## 5. 相关文档（See Also / 参见）

- **端到端流程与状态机（E2E Spec）**: [`docs/01-e2e-flow-and-state-machine.md`](./01-e2e-flow-and-state-machine.md)
- **RAG 深度调优路线图（RAG Roadmap）**: [`docs/technical-reports/rag-tuning.md`](./technical-reports/rag-tuning.md)
- **上下文与提示词（Context & Prompting）**: [`docs/04-context-and-prompting.md`](./04-context-and-prompting.md)
