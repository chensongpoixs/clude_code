# 核心编排模块 (Orchestrator)

项目的“大脑”，负责 Agent 的状态流转、任务拆解与决策逻辑。

## 核心组件
- `agent_loop.py`: 实现 ReAct (Reasoning + Acting) 闭环，管理对话上下文。

## 模块流程
![Orchestrator Flow](module_flow.svg)

