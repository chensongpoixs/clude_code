## glob_file_search（`src/clude_code/tooling/tools/glob_search.py`）业界优化点

### 当前模块职责

- 按 glob 模式查找文件（支持 `**/*.py`），并限制深度/结果数量，避免全仓库扫描导致卡顿。

### 业界技术原理

- **Bounded traversal**：目录遍历与 glob 搜索必须具备 `max_depth/max_results`，否则性能不可控。
- **Ignore by default**：默认忽略 `.git/.clude/node_modules/.venv/__pycache__` 等目录，降低噪音与风险。
- **早停（early stop）**：到达结果上限即停止遍历，避免继续浪费 IO。

### 现状评估（本项目）

- 已实现：`max_results`（默认 200）+ `max_depth`（默认 10）+ 早停。
- 已实现：内置忽略目录集合。

### 可优化点（建议优先级）

- **P1：与 repo ignore 规则统一（单点配置）**
  - **原理**：ignore 规则分散会造成“某工具忽略、另一工具不忽略”。
  - **建议**：把 ignore 规则收敛到 config（或一个 shared helper），glob/grep/list_dir/repo_map 共用。

- **P2：按文件类型的快速过滤**
  - **原理**：在大仓库里，先按后缀过滤比 fnmatch 全匹配更省。
  - **建议**：对模式 `*.{py,ts}` 解析出后缀集合，遍历时先做后缀判断再 fnmatch。


