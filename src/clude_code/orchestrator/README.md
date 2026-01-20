# 核心编排模块 (Orchestrator)

项目的“大脑”，负责 Agent 的状态流转、任务拆解与决策逻辑。

## 核心能力
- **ReAct 循环**: 实现“思考-行动-观测”的自主循环。
- **人格硬化 (Persona Hardening)**: 强化的 System Prompt，确保 Agent 保持工程执行者身份，拒绝推诿。
- **吐字防抖 (Stuttering Detection)**: 自动识别并拦截模型输出的异常重复字符。
- **CoT 自动剥离**: 在存入历史记录前自动剔除思维链（<thought>），减少模型受自身噪音干扰。
- **上下文压缩**: 智能的历史记录裁剪与工具返回结果的结构化压缩。

## 关键文件
- `agent_loop.py`: 主循环实现，集成工具分发与策略校验。

## 函数流程图

`agent_loop.py` 中每个核心函数都有详细的流程图：

1. **`_try_parse_tool_call`** - 从 LLM 输出中解析工具调用 JSON
   - 流程图: ![`agent_loop_parse_tool_call_flow.svg`](../../assets/agent_loop_parse_tool_call_flow.svg)

2. **`_tool_result_to_message`** - 将工具结果转换为结构化消息
   - 流程图: ![`agent_loop_tool_result_to_message_flow.svg`](../../assets/agent_loop_tool_result_to_message_flow.svg)

3. **`AgentLoop.__init__`** - 初始化 Agent 循环
   - 流程图: ![`agent_loop_init_flow.svg`](../../assets/agent_loop_init_flow.svg)

4. **`AgentLoop.run_turn`** - 执行一轮完整的 ReAct 循环
   - 流程图: ![`agent_loop_run_turn_flow.svg`](../../assets/agent_loop_run_turn_flow.svg)

5. **`AgentLoop._trim_history`** - 裁剪对话历史以控制上下文窗口
   - 流程图: ![`agent_loop_trim_history_flow.svg`](../../assets/agent_loop_trim_history_flow.svg)

6. **`AgentLoop._dispatch_tool`** - 根据工具名称分发到对应执行函数
   - 流程图: ![`agent_loop_dispatch_tool_flow.svg`](../../assets/agent_loop_dispatch_tool_flow.svg)

7. **`AgentLoop._semantic_search`** - 执行向量 RAG 语义搜索
   - 流程图: ![`agent_loop_semantic_search_flow.svg`](../../assets/agent_loop_semantic_search_flow.svg)

## 核心规范与协议

为了保证模块化开发的协作精度，我们定义了标准的数据契约：

- **工具协议（Tool Protocol）与权限/沙箱（Policy/Sandbox）**: [`docs/02-tool-protocol.md`](../../../docs/02-tool-protocol.md) - 工具调用消息格式、Schema 校验与权限模型（带中文注释）。
- **端到端流程与状态机（E2E Flow & State Machine）**: [`docs/01-e2e-flow-and-state-machine.md`](../../../docs/01-e2e-flow-and-state-machine.md) - Orchestrator 的状态定义、事件与转移规则。

## 完整执行流程

详细的 Agent 执行流程说明和流程图：

- **执行链路审计与结论（Decision Audit）**: [`docs/17-agent-decision-audit.md`](../../../docs/17-agent-decision-audit.md) - Trace ID / 控制协议 / 重规划的审计结论与 P0 计划。
- **工程路线图（Roadmap）**: [`docs/16-development-plan.md`](../../../docs/16-development-plan.md) - P0/P1/P2 迭代计划与验收标准。
- **动画流程图**: ![Agent Complete Flow](../../assets/agent_complete_flow_animated.svg) - 可视化展示从初始化到返回结果的完整执行路径

## 用户问题流程图（专项）

- **用户问「你可以干嘛啊？」的正确分析流程（专项说明）**: 建议参考 `docs/01-e2e-flow-and-state-machine.md` 中的 `INTAKE/CLARIFYING` 处理原则，并结合 `docs/13-ui-cli-ux.md` 的交互输出规范。
  - 流程图（动画 SVG）: ![用户能力询问分析流程](../../assets/user_query_capabilities_flow_animated.svg)

## 与业界标准对比分析

详细的对比分析文档，识别当前实现与业界标准（Claude Code、Aider、Cursor）的差距：

- **业界对标白皮书（Industry Whitepaper）**: [`docs/technical-reports/industry-whitepaper.md`](../../../docs/technical-reports/industry-whitepaper.md) - 业界能力矩阵与“黄金路径”结论（含中文注释）。
- **编排层健壮性分析（Orchestrator Robustness）**: [`docs/technical-reports/orchestrator-robustness.md`](../../../docs/technical-reports/orchestrator-robustness.md)
- **编排层实现报告（Orchestrator Implementation）**: [`docs/technical-reports/orchestrator-implementation.md`](../../../docs/technical-reports/orchestrator-implementation.md)

### 流程概览

1. **初始化阶段**: 创建 LLM 客户端、工具集、RAG 系统，构建系统提示词
2. **用户输入处理**: 生成 trace_id，提取关键词，更新消息历史
3. **ReAct 循环**（最多 20 次）:
   - LLM 请求 → 响应解析 → 工具调用解析
   - 策略检查（用户确认、命令黑名单）
   - 工具执行 → 结果回喂 → 历史裁剪
4. **返回结果**: AgentTurn（包含最终文本、工具使用标志、追踪ID、事件列表）

## 模块流程
![Orchestrator Flow](module_flow.svg)

