## task_agent（`src/clude_code/tooling/tools/task_agent.py`）业界优化点

### 当前模块职责

- 启动/管理“子代理任务”（SubAgentTask），提供 `run_task` 与 `get_task_status`。

### 业界技术原理

- **异步任务生命周期**：任务应是可异步执行的（RUNNING/COMPLETED/FAILED），并能在 UI 中持续展示进度。
- **避免嵌套 event loop**：在已有事件循环环境中调用 `asyncio.run()` 会报错；业界通常用 `await` 或后台任务队列。
- **任务输出也要做预算**：子任务返回结果可能很长，应按摘要回喂。

### 现状评估（本项目）

- 当前实现是“模拟版”：`run_task` 内使用 `asyncio.run(...)` 同步执行；在某些环境会有兼容风险。

### 可优化点（建议优先级）

- **P0：把执行模型改为真正异步**
  - **建议**：在 orchestrator 中维护 task loop（或线程），`run_task` 只创建任务并返回 task_id；结果通过 `get_task_status` 轮询。

- **P1：任务并发与取消**
  - **建议**：提供 cancel_task；并限制并发数与总预算（避免 fork bomb）。


