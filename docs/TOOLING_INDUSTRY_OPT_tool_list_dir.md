## list_dir（`src/clude_code/tooling/tools/list_dir.py`）业界优化点

### 当前模块职责

- 列出目录内容，返回结构化条目列表（name/is_dir），并提供 `max_items/include_size` 以控制输出体积。

### 业界技术原理

- **分页/截断优先**：目录可能非常大，必须提供 `max_items` 与 `truncated/total_count` 信息用于决策。
- **目录优先排序**：目录比文件更能帮助模型决定下一步（继续下钻还是读文件）。
- **最小必要字段**：默认不返回 size/mtime 等低信号字段，避免 token 浪费；需要时再显式开启。

### 现状评估（本项目）

- 已实现：`max_items` 默认 100；`include_size` 默认 False；目录优先排序；截断时返回统计字段。

### 可优化点（建议优先级）

- **P1：加入 `include_hidden` 与 ignore 规则**
  - **原理**：隐藏目录（.git/.clude）通常不应默认展示。
  - **建议**：默认排除隐藏文件夹，允许显式开启；并统一复用 ignore_dirs 规则（与 glob/grep 对齐）。

- **P2：加入 `depth`（递归列举）但强制分页**
  - **原理**：一次性递归列举会爆炸；但适度 depth=2 对“理解项目结构”很有帮助。
  - **建议**：只允许小深度，并返回 tree-like 摘要结构。


