# Phase 3：llama.cpp 严格 role 交替 —— “消息序列规范化/合并”落地报告

> 生成日期：2026-01-13  
> 相关文件：`src/clude_code/orchestrator/agent_loop.py`、`src/clude_code/llm/llama_cpp_http.py`

---

## 1. 背景：为什么一定要做“发送前规范化”

在 llama.cpp 的部分 chat template 中，`/v1/chat/completions` 会对 messages 做模板级硬校验：  
**system 之后必须严格 user/assistant 交替**，否则直接返回 500（不是 4xx）。

这与 OpenAI 官方接口的“允许多轮同角色消息”不同，因此需要 adapter 层兜底。

---

## 2. 复盘问题是如何产生的（基于 traceback 证据链）

你现场的 messages 序列中出现了：

- `role='user'`：工具结果回喂（tool_result）
- `role='user'`：下一轮 step_prompt

也就是连续 **user/user**，触发：

- `Conversation roles must alternate user/assistant/user/assistant/...`

**关键点**：这不是模型输出问题，而是“编排器构造请求 payload”违反了后端模板契约。

---

## 3. 设计目标（业界同等稳健）

### 3.1 约束

- **不改业务逻辑**：Planner/Executor 的结构不动，只修正“送出去的 messages”。
- **单点修复**：避免在每个“回喂/提示”处插各种 if。
- **可观测**：发生了合并/修正必须可追踪（否则调试会更难）。

### 3.2 业界常见技术路线

| 路线 | 代表实践 | 说明 |
|---|---|---|
| A | tool role / tool messages | 如果后端模板支持 tool role，最干净 |
| B | Observation 放 assistant | 把工具结果作为 assistant 的一部分，保证交替 |
| C | 输入序列 normalizer | 发送前合并连续同角色，最通用 |

本项目选择 **C**：原因是 llama.cpp 模板差异大、兼容性碎片化，**normalizer 最稳**。

---

## 4. 本项目实现（统一出口）

### 4.1 落地点

在 `AgentLoop.run_turn()` 内新增：

- `_normalize_messages_for_llama(stage, step_id=None)`：只负责把 `self.messages` 变成“模板可接受形态”
- `_llm_chat(stage, step_id=None)`：所有 `self.llm.chat(...)` 的唯一出口

### 4.2 规范化规则（关键）

1. **多 system 合并到第一条 system**  
2. **system 后如果出现 assistant**（理论上不该出现，但真实场景会有）：并入 system  
3. **连续 user/user**：合并为一个 user（中间用空行分隔）  
4. **连续 assistant/assistant**：同理合并  
5. 发生合并时，发出事件：
   - `messages_normalized`（包含 before/after、合并次数、stage/step_id）

---

## 5. 与业界对比结论

| 维度 | 业界（Cursor/Claude Code/Aider） | 本项目（落地后） |
|---|---|---|
| 修复方式 | adapter 层兜底（normalize/convert） | ✅ 统一出口 `_llm_chat` |
| 影响范围 | 单点，避免散落 if | ✅ 单点 |
| 可观测性 | 关键事件可追踪 | ✅ `messages_normalized` |
| 兼容性 | 面向多模型、多模板 | ✅ 合并策略最通用 |

**结论**：该修复属于“业界标配的 adapter 层契约修正”，能显著提升本地推理栈的稳定性。

---

## 6. 后续可选增强（不影响当前落地）

1. **可配置策略**：merge/insert dummy assistant/convert tool role  
2. **合并可读性**：合并时加标签（例如 `[tool_result]` / `[step_prompt]`）  
3. **更严格不变式检查**：发送前 assert + 自动修复 + 指标统计


