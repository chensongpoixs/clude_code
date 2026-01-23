## LocalTools 门面（`src/clude_code/tooling/local_tools.py`）业界优化点

### 当前模块职责

- 将 `tooling/tools/*.py` 的实现统一封装为一个对象（`LocalTools`），供 orchestrator 调用。

### 业界技术原理

- **Thin facade（门面尽量薄）**：门面层只做依赖注入（workspace_root/limits）和参数透传；复杂策略放在分发层（dispatch）或工具内部。
- **统一资源预算**：max_file_read_bytes/max_output_bytes 等必须从配置注入，保持可调，避免“写死上限”导致在不同模型窗口下行为不稳。

### 现状评估（本项目）

- `LocalTools` 作为统一入口封装所有工具实现；read_file/run_cmd 等已注入预算参数。

### 进一步可优化点

- **P1：参数契约一致性（LocalTools vs ToolSpec）**
  - **原理**：ToolSpec schema 与 LocalTools 签名不一致，会导致“校验通过但调用失败”。  
  - **建议**：在 `clude tools --validate` 中自动对比 ToolSpec.args_schema 与 LocalTools 方法签名（或至少保证 example_args 可跑通）。

- **P2：批量工具（batching）**
  - **原理**：业界会提供 `read_many_files([...])`、`grep_multi([...])` 以减少 tool-call roundtrip 与回喂 token。  
  - **建议**：新增批量工具，回喂仅输出每个文件的摘要/定位（不要回传全文）。

{
  "cells": [],
  "metadata": {
    "language_info": {
      "name": "python"
    }
  },
  "nbformat": 4,
  "nbformat_minor": 2
}