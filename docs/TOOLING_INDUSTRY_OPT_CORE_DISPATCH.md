## 工具规范/分发层（`orchestrator/agent_loop/tool_dispatch.py`）业界优化点

### 当前模块职责

- **单一事实源（Single Source of Truth）**：`ToolSpec` 统一承载工具的 name/summary/schema/example/side_effects 等“工具事实”。  
- **统一入口分发**：`dispatch_tool()` 是执行工具的中心点（参数校验、执行、错误兜底、缓存接入）。  

### 业界技术原理

- **Contract-first / Schema-first**：工具调用必须可机器校验，减少“模型随意拼参”。常见实践：
  - JSON Schema + `additionalProperties=false`
  - default 真正生效（不把默认逻辑散落到 handler 里）
  - enum/范围约束（降低无效调用）
- **Single choke point**：缓存、指标、超时、风险开关尽量放在统一入口，避免每个工具重复实现、重复出错。
- **Fail-closed（对参数）/ Fail-open（对优化）**：
  - 参数不合法必须拒绝（fail-closed）
  - 缓存/度量等性能优化失败不能影响工具可用性（fail-open）

### 现状评估（本项目）

- **参数强校验**：`ToolSpec.validate_args()` 已在分发前执行（对齐业界）。  
- **工具清单渲染**：system prompt 默认只注入“简洁示例”，避免 system prompt 过长（对齐业界）。  
- **缓存入口（已接入）**：`dispatch_tool()` 已接入会话级缓存：命中直接返回并标记 `from_cache=true`；写操作后保守 `cache.clear()` 失效。  

### 进一步可优化点（建议优先级）

- **P0：ToolSpec 与实现一致性审计自动化**
  - **原理**：把“schema/example/handler”一致性做成 CI/doctor 检查，防止回归。
  - **建议**：在 `clude tools --validate/--audit` 中增加：schema default 覆盖率、required 覆盖率、deprecated/版本分布、外部依赖缺失清单。

- **P1：统一超时/取消（cancellation）语义**
  - **原理**：业界工具系统通常提供“超时 + 可取消”，避免工具卡死导致 agent loop 卡死。
  - **建议**：ToolSpec 使用 `timeout_seconds`，并在分发层统一应用（工具内部已有 timeout 的以更小者为准）。

- **P1：细粒度缓存失效（从 clear → path-aware）**
  - **原理**：写操作只影响少量路径，全清会降低命中率。
  - **建议**：维护 `path -> set(cache_key)` 反向索引，写操作仅失效相关 key。

- **P2：工具热排序（hot ranking）与意图动态工具集闭环**
  - **原理**：减少“可选工具集合”显著降低 token 与误用概率。
  - **建议**：结合 Registry metrics 做“热工具优先 + 冷工具隐藏”，并写入 system prompt 的工具段落。

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