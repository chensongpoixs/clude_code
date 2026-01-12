# 可观测性模块

负责记录 Agent 的全量行为日志，包括审计日志和调试轨迹。

## 核心组件
- `audit.py`: 记录关键行为（工具调用、修改操作）的 JSONL 审计日志。
- `trace.py`: 记录详细的执行轨迹，用于问题复现与流程分析。

## 模块流程
![Observability Flow](module_flow.svg)

