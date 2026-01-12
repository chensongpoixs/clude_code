# 工具箱与回馈模块 (Tooling)

负责具体的本地能力实现，并对结果进行语义化加工。

## 核心组件
- `local_tools.py`: 包含文件读写、Grep 搜索、Patch 应用及 Repo Map 生成等核心能力。
- `feedback.py`: 将工具执行的原始 Payload 转化为模型更易理解的结构化回馈。

## 模块流程
![Tooling Flow](module_flow.svg)

