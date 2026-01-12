# 工具箱与回馈模块 (Tooling)

负责具体的本地能力实现，并对结果进行语义化加工。

## 核心能力
- **Patch Engine**: 支持 `apply_patch` (模糊匹配/多点替换) 与 `undo_patch` (哈希校验回滚)。
- **高效搜索**: 集成 `ripgrep` (rg) 进行高性能代码搜索，并支持 `glob_file_search`。
- **语义采样 (Semantic Sampling)**: 在 `feedback.py` 中实现了 ±10 行动态窗口，并优先保留逻辑锚点（if/for/return）。
- **仓库地图 (Repo Map)**: 利用 `ctags` 生成轻量级的符号拓扑，为模型提供全局视野。

## 关键文件
- `local_tools.py`: 包含文件读写、Grep 搜索、Patch 应用及 Repo Map 生成等核心能力。
- `feedback.py`: 将工具执行的原始 Payload 转化为模型更易理解的结构化回馈。

## 模块流程
![Tooling Flow](module_flow.svg)

