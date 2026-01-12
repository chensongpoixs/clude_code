# 01｜端到端流程与状态机（可实现规格）

本章给出一个可直接实现的“会话-计划-工具执行-验证-总结”的状态机，用于代理编排（Orchestrator）。

## 1. 端到端流程（E2E）

### 1.1 典型一次任务回合
1. 用户输入任务（自然语言）
2. 解析与澄清（可选：提出 1~3 个关键问题）
3. 构建上下文（仓库信息 + 相关文件片段 + 历史对话）
4. 生成计划（todo/steps，包含验证策略）
5. 执行步骤循环：
   - 调用搜索/读取文件
   - 生成修改（补丁/写文件）
   - 运行 lint/test/build（按策略）
   - 根据结果修复
6. 输出总结（改了什么、为什么、如何验证、风险与回滚）
7. 可选：生成 git commit / PR 描述

### 1.2 失败时的恢复路径
- 工具失败：重试 → 降级工具（语义检索失败则回退 grep）→ 请求用户协助（例如缺依赖）
- 修改失败（编译不过）：最小化修复 → 回滚最近 patch → 重新规划
- 需求不清：停止执行，输出澄清问题并等待

## 2. Orchestrator 状态机

### 2.1 状态定义
- `IDLE`：等待用户输入
- `INTAKE`：解析输入、权限与风险预判
- `CLARIFYING`：提出澄清问题（可选）
- `CONTEXT_BUILDING`：收集上下文（文件树、搜索结果、文件片段）
- `PLANNING`：生成计划（步骤、依赖、验证）
- `EXECUTING`：按步骤执行（调用工具）
- `VERIFYING`：运行 lint/test/build 或自定义验证
- `SUMMARIZING`：生成总结与下一步建议
- `AWAITING_CONFIRMATION`：危险操作等待确认（写/删/执行/推送）
- `RECOVERING`：处理失败，重试/回滚/降级
- `DONE`：本轮结束

### 2.2 事件（Events）
- `USER_MESSAGE(text)`
- `CLARIFICATION_ANSWER(text)`
- `TOOL_CALL_REQUEST(name, args)`
- `TOOL_CALL_RESULT(name, ok, payload)`
- `CONFIRM(yes/no, scope)`
- `TIMEOUT`
- `CANCEL`

### 2.3 转移规则（摘要）
- `IDLE` + `USER_MESSAGE` → `INTAKE`
- `INTAKE`：
  - 若缺关键上下文 → `CLARIFYING`
  - 否则 → `CONTEXT_BUILDING`
- `CONTEXT_BUILDING` → `PLANNING`
- `PLANNING`：
  - 若计划包含危险动作 → `AWAITING_CONFIRMATION`
  - 否则 → `EXECUTING`
- `EXECUTING`：
  - 任一步失败 → `RECOVERING`
  - 步骤完成 → `VERIFYING`
- `VERIFYING`：
  - 通过 → `SUMMARIZING`
  - 失败 → `RECOVERING`
- `RECOVERING`：
  - 可修复 → 回到 `EXECUTING`（生成修复步骤）
  - 不可修复 → `SUMMARIZING`（输出阻塞与手工步骤）
- `SUMMARIZING` → `DONE` → `IDLE`

## 3. 计划模型（Plan/Todo）数据结构

建议将计划抽象成可序列化结构，便于审计与回放。

### 3.1 Plan
- `plan_id: string`
- `goal: string`
- `constraints: string[]`（例如“不得改 API”、“不能访问网络”）
- `steps: Step[]`
- `verification: VerificationPolicy`
- `risk_level: low|medium|high`
- `created_at: timestamp`

### 3.2 Step
- `step_id: string`
- `title: string`
- `intent: string`（为什么做）
- `tool_calls: ToolCallTemplate[]`（可选：预期要调用的工具）
- `expected_artifacts: Artifact[]`（例如修改文件列表）
- `status: pending|in_progress|done|blocked|skipped`
- `rollback_hint: string`（可选：如何撤销）

### 3.3 VerificationPolicy
- `mode: none|lint|test|build|custom`
- `commands: string[]`（例如 `npm test`）
- `required: boolean`
- `stop_on_fail: boolean`

## 4. 执行控制：重试、幂等与回滚

### 4.1 重试策略（工具层通用）
- 只对“幂等读取类工具”默认重试（read/search）
- 对“写/执行类工具”不自动重试，必须由 Orchestrator 决策
- 指数退避：\(200ms, 500ms, 1s\)，最多 3 次（可配置）

### 4.2 幂等要求
- `read_file/search`：幂等
- `apply_patch/write_file/delete_file`：非幂等，必须具备“预检 + 回滚”
- `run_terminal_cmd`：默认非幂等，需要安全策略与确认

### 4.3 回滚机制（建议两层）
- **补丁级回滚**：每次写入保存逆向 patch
- **Git 级回滚（可选）**：每个任务开分支或保存临时 commit

## 5. 失败分类与错误码（建议统一）

### 5.1 失败分类
- `E_POLICY_DENIED`：策略拒绝（越权路径/危险命令/网络）
- `E_IO`：文件系统错误
- `E_TOOL_TIMEOUT`：工具超时
- `E_INVALID_ARGS`：参数不合法（schema 校验失败）
- `E_CONFLICT`：补丁冲突/并发写冲突
- `E_BUILD_FAIL`：构建/测试失败
- `E_MODEL`：模型输出不符合协议/解析失败

### 5.2 错误处理原则
- 给用户“下一步可操作建议”
- 对内部错误保留 trace_id，外部隐藏敏感信息


