# 安全策略模块 (Policy)

负责在工具执行前进行安全审计与权限校验。

## 核心组件
- `command_policy.py`: 命令黑白名单校验，防止执行危险或越权指令。

## 模块流程
![Policy Flow](module_flow.svg)

