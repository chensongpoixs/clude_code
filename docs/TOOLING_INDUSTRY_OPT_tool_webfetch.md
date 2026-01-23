## webfetch（`src/clude_code/tooling/tools/webfetch.py`）业界优化点

### 当前模块职责

- 抓取网页内容并缓存为 Markdown（默认 `.clude/markdown/`），带 YAML front matter 元信息与过期时间；支持索引文件加速查找。

### 业界技术原理

- **Cache-aside**：优先读缓存，miss 再抓取；并提供强制刷新开关。
- **输入验证**：只允许 http/https，避免 `file://` 等本地协议造成信息泄露。
- **内容预算（budgeting）**：抓取内容必须按 max_content_length 截断，避免回喂爆炸。

### 现状评估（本项目）

- 已实现：缓存目录与索引、TTL、缓存扫描只读前缀、文件名净化（Windows 兼容）。
- 仍需结合回喂层确保“只回传 preview + 元信息”（避免把整篇文章塞进 messages）。

### 可优化点（建议优先级）

- **P1：ETag/Last-Modified 条件请求**
  - **原理**：缓存过期后也可用条件请求减少带宽与延迟。
  - **建议**：在 front matter 中记录 etag/last_modified，并在刷新时带 `If-None-Match/If-Modified-Since`。

- **P2：正文抽取策略分层**
  - **原理**：不同网页结构差异大；业界通常有“阅读模式/主内容提取器”。
  - **建议**：引入可选提取器（Readability/Trafilatura），失败回退原始 HTML→Markdown。


