# 05 | 计划分解与任务执行（可实现规格）(Planning & Tasking Spec)

> **Status (状态)**: Stable Spec (稳定规格，可直接落地实现)  
> **Audience (读者)**: Maintainers / Orchestrator Engineers (维护者/编排工程师)  
> **Goal (目标)**: 定义 Agent 如何将模糊需求转化为可执行步骤（Plan/计划），并在执行中维护 Todo Runtime（任务运行时）与重规划（Re-planning/重规划）机制。

本规范定义 Agent 如何把“模糊需求”转化为“可执行步骤”。通过显式计划（Explicit Planning/显式规划）机制，增强复杂任务（如跨文件重构）中的逻辑严密性与可解释性。

---

---

## 1. 计划生成器 (Planner/规划器)

在接收到复杂任务后，Agent 会优先进入 `PLANNING` 状态。

### 1.1 计划三要素
- **子任务拆解**: 将大目标分解为 3-7 个原子步骤。
- **依赖分析**: 明确步骤间的先后顺序（如“先定义接口，再实现类”）。
- **验证预案**: 为每个关键步骤预设一个校验动作（如“运行特定测试用例”）。

### 1.2 风险评估
- 自动识别“破坏性”动作（如修改核心支付逻辑、删除配置文件）。
- 针对高风险计划，强制要求用户确认后方可进入执行。

---

---

## 2. 任务运行时 (Todo Runtime/任务运行时)

Agent 会维护一个动态的 Todo 列表，并根据执行反馈实时更新。

| 状态 | 说明 |
| :--- | :--- |
| **Pending** | 计划中，尚未开始 |
| **In Progress** | 当前正在调用的工具所归属的任务 |
| **Completed** | 工具返回成功，且验证通过 |
| **Failed** | 工具报错或验证失败，需要重规划 |
| **Skipped** | 由于前置失败或逻辑变更，该步骤已不再需要 |

> **约束（Constraint/约束）**：同一时刻只允许一个步骤处于 `In Progress`，避免并发导致的状态错乱（尤其涉及写文件/执行命令时）。

---

---

## 3. 动态重规划 (Re-planning/动态重规划)

Agent 必须具备在执行中“见招拆招”的能力：
- **发现新线索**: 当 `grep` 发现原计划未覆盖的关键文件时，自动插入“读取该文件”的步骤。
- **处理失败**: 当补丁应用冲突时，自动生成“读取最新内容并生成新补丁”的修复任务。
- **环境变更**: 当检测到缺少依赖（如 `npm install` 失败）时，向用户请求授权安装。

> **推荐机制（Recommendation/建议）**：优先采用“局部重规划（Plan Patch/计划补丁）”，只对受影响步骤做增量调整，避免全量重写导致上下文遗忘与 Token 浪费。

---

---

## 4. 结论 (Conclusion/结论)

“先计划再执行”是区分 Code Agent 与普通 Chatbot 的重要标志。通过显式的计划分解，我们不仅提升了复杂任务的成功率，更让 Agent 的执行轨迹变得清晰、可预测且具备人类可理解的逻辑感。

---

## 5. 相关文档（See Also / 参见）

- **端到端流程与状态机（E2E Spec）**: [`docs/01-e2e-flow-and-state-machine.md`](./01-e2e-flow-and-state-machine.md)
- **上下文构建与提示词（Context Spec）**: [`docs/04-context-and-prompting.md`](./04-context-and-prompting.md)
- **代码编辑与补丁系统（Patching Spec）**: [`docs/06-code-editing-and-patching.md`](./06-code-editing-and-patching.md)
