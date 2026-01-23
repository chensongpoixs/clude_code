## question（`src/clude_code/tooling/tools/question.py`）业界优化点

### 当前模块职责

- 生成一个“待用户回答”的结构化问题（当前实现返回 `status=pending`），用于澄清需求/收集选择。

### 业界技术原理

- **Human-in-the-loop gate**：在高风险或高歧义点，工具应显式把控制权交还用户。
- **可序列化的问答协议**：问题对象应包含 `id/type/options/multiple/default/validation`，便于 UI 与会话恢复。
- **阻塞语义要清晰**：如果工具返回 pending，orchestrator 必须理解“本轮不可继续执行”。

### 现状评估（本项目）

- 现实现更像“问题对象构造器”，不真正读取用户输入；这在 CLI 体系中容易造成：
  - agent 继续往下走（把 pending 当作已回答）
  - 或进入循环（不断重复提问）

### 可优化点（建议优先级）

- **P0：明确 question 的控制协议与阻塞语义**
  - **建议**：返回 payload 增加 `question_id`；并由 chat handler 捕获该事件进入“等待输入”态，收到用户输入后再把 answer 写回历史。

- **P1：参数与校验增强**
  - **建议**：options 为空时禁止 multiple；限制 question 长度；提供默认选项/必选约束。


