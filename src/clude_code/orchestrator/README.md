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

## 模块流程
![Orchestrator Flow](module_flow.svg)

