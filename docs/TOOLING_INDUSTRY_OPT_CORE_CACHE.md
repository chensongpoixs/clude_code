## 会话级工具结果缓存（`src/clude_code/tooling/tool_result_cache.py`）业界优化点

### 当前模块职责

- 提供会话级 LRU + TTL 缓存，减少重复 IO/网络查询，并降低回喂 token。

### 业界技术原理

- **Determinism boundary**：只缓存“读/确定性”工具（如 read_file/list_dir/grep/glob），避免缓存副作用或强时效数据。
- **Key canonicalization**：缓存键必须对参数排序/规范化，避免“同参不同序”导致 miss。
- **Invalidation-first**：写操作后必须失效，否则会把旧事实喂给模型，引发错误计划。

### 现状评估（本项目）

- `ToolResultCache` 已实现：LRU、TTL、stats、保守失效（clear）。
- 已在 `dispatch_tool()` 统一接入：命中返回 `from_cache=true`。

### 进一步可优化点

- **P0：path-aware 精准失效（替代 clear） (✅ 核心改进建议)**
  - **原理**：写操作通常只影响少量文件。
  - **技术实现**:
    - **Key 结构化**: 缓存 Key 需包含操作涉及的所有路径（Path Set）。
    - **监听机制**: 当 `write_file(path="A")` 执行成功时，遍历缓存桶，剔除所有 Path Set 中包含 "A" 的条目。
    - **收益**: 在多文件编辑场景下，未改动文件的读取、搜索结果可以跨轮次持久命中，极大提升复杂任务响应速度。

- **P1：对 webfetch/websearch 做更短 TTL 或按 provider 分层**
  - **原理**：搜索结果时效性强。  
  - **建议**：对 network 工具默认 TTL=60s，file 工具 TTL=300s。

- **P1：缓存与度量联动**
  - **原理**：命中率与节省 token 是调参依据。  
  - **建议**：把 cache hit/miss 纳入 ToolRegistry/observability，并在 `doctor` 中输出。

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