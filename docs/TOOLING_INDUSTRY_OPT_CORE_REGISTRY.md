## 工具注册/度量（`src/clude_code/tooling/tool_registry.py`）业界优化点

### 当前模块职责

- 维护工具的分类、优先级、废弃标记。
- 记录调用次数、成功率、平均耗时等指标，供审计/优化使用。

### 业界技术原理

- **Operational visibility**：工具系统本质是“可观测的执行系统”，指标是做优化/排障的基础。
- **Hot path governance**：用 metrics 驱动“默认暴露哪些工具、提示词里注入多少工具”，降低误用与 token 消耗。

### 现状评估（本项目）

- 具备注册、分类、监听器与基础 metrics 的框架能力。

### 进一步可优化点

- **P0：指标字段语义修正与统一**
  - **原理**：指标一旦语义错误会误导所有决策（热排序、SLO、回归分析）。  
  - **建议**：`last_used` 应记录时间戳而非 duration；并补充 p50/p95（粗略也可）。

- **P1：把 ToolSpec.cacheable/timeout/side_effects 与 Registry 联动**
  - **原理**：这些字段用于治理（是否注入提示词、是否允许模型调用、是否需要确认）。  
  - **建议**：Registry 提供“按意图/风险/热度”的工具集合视图，供 system prompt 动态渲染。

- **P2：输出审计报告（对标业界 doctor）**
  - **建议**：`clude tools --audit` 输出：重复 name、deprecated 使用、schema 覆盖率、外部依赖缺失清单、近 N 次失败工具榜单。

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