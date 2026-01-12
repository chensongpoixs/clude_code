# 业界级功能升级：可行性评估与实现方案 (Industry Upgrade)

本文件评估了将 Clude-Code 核心模块升级至业界顶尖水平（Aider/Cursor/Claude Code 级别）的技术路径。

---

## 1. 语义化回喂 (Semantic Feedback)

### 1.1 业界对标
- **Cursor**: 使用本地 Embedding 模型对长文件进行向量切片，只回传与 Query 相关的 chunk。
- **Claude Code**: 结合检索工具动态决定回传深度。

### 1.2 问题分析与风险
- **计算瓶颈**：本地 CPU 跑 llama.cpp 时，并行跑 Embedding 会导致推理严重掉速。
- **冷启动**：首次运行需要扫描全量代码生成向量，用户等待感强。

### 1.3 我们的实现思路 (Hybrid Approach)
1. **启发式先行**：保留当前 `feedback.py` 的逻辑作为兜底。
2. **关键词加权**：从用户的指令中提取关键词（Key Phrases），在 `read_file` 或 `grep` 结果中，优先保留包含关键词的行及其上下 5 行（Windowing）。
3. **延迟评估**：仅当单次 Payload > 8KB 时触发。

---

## 2. 索引加速搜索 (Indexed Search via Repo Map)

### 2.1 业界对标
- **Aider**: 核心技术是 `Repo Map`，通过 ctags 提取所有符号，构建一个 10KB 左右的“全景图”塞给提示词。

### 2.2 问题分析与风险
- **依赖性**：强制要求用户安装 `universal-ctags`。
- **语言覆盖**：ctags 对动态语言（Python/JS）支持好，但对某些 DSL 支持差。

### 2.3 我们的实现思路
1. **集成 ctags**：在 `LocalTools` 中新增 `generate_repo_map` 方法。
2. **符号过滤**：只提取 Class、Function、Method，过滤局部变量。
3. **动态注入**：在 System Prompt 之后增加一个 `[Repository Structure]` 块，模型不再“盲目搜索”。

---

## 3. 闭环修复式诊断 (Auto-Fixing Doctor)

### 3.1 业界对标
- **Claude Code**: 能够自行决定是否需要 `npm install` 修复环境。

### 3.2 问题分析与风险
- **安全性**：模型自动执行安装命令可能被利用执行恶意脚本。
- **多样性**：Windows (choco/scoop/conda), Mac (brew), Linux (apt/yum) 环境极度复杂。

### 3.3 我们的实现思路
1. **交互式修复**：`clude doctor --fix`。
2. **命令生成器**：根据当前 OS 和 shell 环境，生成对应的安装建议。
3. **干跑模式 (Dry Run)**：先打印命令，用户确认后通过 `run_cmd` 执行。

---

## 4. 评估结论

| 模块 | 优先级 | 可行性评分 | 结论 |
| :--- | :--- | :--- | :--- |
| **Repo Map (索引)** | **P0** | 9.5/10 | **建议立即开始**。这是对标 Aider 的核心。 |
| **Auto-Fix Doctor** | **P1** | 8.0/10 | **建议作为可选参数**实现。 |
| **语义回喂** | **P2** | 6.5/10 | **建议先观察**，目前启发式摘要在本地模型下性价比更高。 |

