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

## 模块流程
![Orchestrator Flow](module_flow.svg)

