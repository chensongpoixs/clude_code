# 03｜仓库索引与检索（Repo Indexing & Retrieval）

目标：在“超大仓库/多语言/多构建系统”下，仍能在秒级定位相关代码，并为上下文构建提供高质量候选片段。

## 1. 子模块拆分

### 1.1 文件树与元数据（File Catalog）
- **职责**：列出 workspace 下文件、大小、修改时间、是否二进制、语言推断
- **输入**：workspace 路径、ignore 规则（.gitignore/.cursorignore/自定义）
- **输出**：`FileEntry[]`
- **实现要点**：
  - 增量更新：基于 mtime/哈希
  - 忽略规则合并：gitignore + 产品 ignore
  - 大文件与二进制文件识别（阈值可配置）

### 1.2 精确搜索（Grep/Ripgrep Adapter）
- **职责**：高性能文本搜索（regex、大小写、glob）
- **输入**：pattern、path scope、glob、head_limit
- **输出**：`SearchHit[]`（文件、行号、上下文）
- **实现要点**：
  - 封装 `rg` 或内置搜索；输出统一结构
  - 结果裁剪：按文件/总行数上限

### 1.3 语义检索（Semantic Search，可选）
- **职责**：基于 embedding 的语义相似度召回
- **输入**：query、目录 scope、top_k
- **输出**：`SemanticHit[]`（chunk_id、score、文件/行范围）
- **实现要点**：
  - chunk 策略：按函数/类（优先）、或按固定窗口
  - 向量库：本地 SQLite/FAISS/自研（可替换）
  - 异步索引构建：首次缺索引时降级到 grep

### 1.4 符号索引（Symbol Index，可选）
- **职责**：定义/引用、跳转、调用链
- **实现**：对接 LSP（tsserver、pyright、gopls…）或 ctags/tree-sitter

## 2. 数据结构（建议）

### 2.1 FileEntry
- `path: string`
- `size_bytes: number`
- `mtime_ms: number`
- `is_binary: boolean`
- `language?: string`

### 2.2 SearchHit（grep）
- `path: string`
- `line: number`
- `column?: number`
- `preview: string`
- `before?: string[]`
- `after?: string[]`

### 2.3 CodeChunk（语义索引用）
- `chunk_id: string`
- `path: string`
- `start_line: number`
- `end_line: number`
- `content_hash: string`
- `tokens_estimate?: number`

## 3. 索引生命周期

### 3.1 构建触发
- 首次打开 workspace
- 用户显式命令 `index build`
- 文件系统变更（watcher）触发增量更新

### 3.2 存储位置
- `.clude/`（建议）：
  - `index.sqlite`
  - `chunks/`（可选：按文件缓存）
  - `logs/`

### 3.3 失效策略
- 文件 content_hash 变化 → 对应 chunk 失效重建
- ignore 规则变化 → 全量重建或目录级重建

## 4. 与 Context Builder 的接口

### 4.1 推荐 API（内部）
- `listFiles(scope) -> FileEntry[]`
- `grep(pattern, scope) -> SearchHit[]`
- `semanticSearch(query, scope, top_k) -> SemanticHit[]`
- `getFileSnippet(path, start_line, end_line) -> string`

### 4.2 召回融合（策略）
- 默认：语义 top_k + grep top_k（去重）
- 评分合并：语义分数 + 词法匹配加权 + 距离用户文件的“邻近度”

## 5. MVP 实现建议
- 先做：文件树 + grep + read_file（即可完成 80% 任务）
- 再做：语义索引（异步，失败可降级）
- 最后做：符号索引（提升“改动影响面”分析能力）


