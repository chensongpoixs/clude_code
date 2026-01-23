## todo_manager（`src/clude_code/tooling/tools/todo_manager.py`）业界优化点

### 当前模块职责

- 提供简单的 todo 列表：创建/更新（`todowrite`）与读取（`todoread`）。

### 业界技术原理

- **状态机明确**：todo 是 agent 自己的执行状态，字段应稳定（id/status/priority/created_at/updated_at）。
- **存储可靠性**：业界通常会把 todo 存在会话目录或 `.clude/` 下（可恢复、可审计），而不是纯内存。
- **API 不要“借字符串协议”**：`content.startswith("update:")` 这种约定非常脆弱，容易被模型误用。

### 现状评估（本项目）

- 有数据结构与基础 CRUD，但默认没有持久化（`TodoManager()` 未传 storage_path）。
- `todowrite` 用 `content` 字符串携带更新语义，属于“脆弱协议”。

### 可优化点（建议优先级）

- **P0：把更新协议改为显式字段**
  - **建议**：`todowrite(todo_id: str | None, content: str, status: ..., priority: ...)`；由 schema 强校验保证正确性。

- **P1：会话级持久化**
  - **建议**：将 storage_path 指向 `.clude/session/{session_id}/todos.json`（或 session store 目录），并在会话恢复时加载。


