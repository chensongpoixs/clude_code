## read_file（`src/clude_code/tooling/tools/read_file.py`）业界优化点

### 当前模块职责

- 读取工作区文件内容，支持 `offset/limit` 按行切片；并对大文件执行内存/输出上限治理。

### 业界技术原理

- **流式/分块读取（streaming I/O）**：避免 `read_bytes()` 把整文件载入内存，尤其是大仓库/日志文件。
- **采样优先（sampling over dumping）**：对超大文件优先“头尾采样 + 省略标记”，确保模型保留上下文中最关键的结构信息。
- **定位优先（offset/limit）**：工具链应鼓励“先 grep 再 read_file(offset/limit)”。

### 现状评估（本项目）

- 已实现：`_read_file_streaming()`，对大文件采用流式读取；未提供 offset 时采用头尾采样；提供 offset 时做行跳过+限制读取。
- 回喂层已支持关键词窗口采样（`tooling/feedback.py`）。

### 可优化点（建议优先级）

- **P0：避免“二次全量扫描”统计 total_lines**
  - **现状**：offset 模式下会先 `sum(1 for _ in f)` 统计总行数，等价于完整扫描一次。
  - **原理**：在大文件上会造成额外 IO 与延迟。
  - **建议**：total_lines 改为可选字段（仅在小文件或用户显式请求时计算），或用近似估计。

- **P1：二进制/超长行治理 (✅ 待完善)**
  - **原理**：二进制文件或超长单行会破坏 token 预算与可读性。
  - **规范**：
    - **检测机制**: 读取前 N 字节判断不可打印字符比例 (>30% 视为二进制)。
    - **处理方式**: 拒绝返回正文，仅返回文件元信息（size/mtime/mime_type）。
    - **超长行**: 单行超过 1000 字符时，执行行内截断并标注 `[line truncated]`。

- **P1：返回“内容指纹”**
  - **原理**：为后续 patch/undo/缓存失效提供依据。
  - **建议**：返回 `sha256_prefix`（或 file mtime + size）作为弱一致性标识。


