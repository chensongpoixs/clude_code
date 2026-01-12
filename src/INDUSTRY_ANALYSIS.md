# 业界技术对比分析与 clude-code 选型结论 (src/)

本报告对比了 **clude-code** 与业界主流 Code Agent（Claude Code, Aider, Cursor, OpenDevin）的技术方案，分析当前进度并给出演进结论。

---

## 1. 业界 Code Agent 技术路线比较

| 维度 | **Claude Code (Anthropic)** | **Aider** | **Cursor (IDE)** | **clude-code (本项目)** |
| :--- | :--- | :--- | :--- | :--- |
| **部署形态** | 本地 CLI | 本地 CLI (Git 深度绑定) | IDE 嵌入 | **本地 CLI (Python)** |
| **模型接入** | Claude 3.5 Sonnet (API) | 多模型 (OpenRouter/Local) | 闭源托管模型 | **llama.cpp HTTP (本地优先)** |
| **代码编辑** | 工具调用 (Bash/Write) | **Unified Diff / Search-Replace** | 原生编辑器 Buffer 改动 | **全量写入 -> Patch (规划中)** |
| **上下文管理** | 动态工具召回 | 仓库图 (Repo Map) | 高性能嵌入检索 (RAG) | **全量历史 -> 动态裁剪 (规划中)** |
| **核心优势** | 工具理解力强，Bash 权限大 | 编辑极其精准，极省 Token | 体验无缝，多文件 RAG 强 | **全量本地化、协议可控、模块化** |

---

## 2. 核心技术分析与 clude-code 现状

详见技术原理深度白皮书：[`src/INDUSTRY_CODE_AGENT_TECH_WHITEPAPER.md`](INDUSTRY_CODE_AGENT_TECH_WHITEPAPER.md)

### 2.1 模型编排 (Orchestration)
- **业界方案**: 大多采用“计划-执行-验证”的状态机。Claude Code 擅长通过 Bash 工具自行探索。
- **最佳实践**: **ReAct (Reasoning + Acting) 闭环**（详见白皮书）。
- **clude-code 现状**: 实现了基础的 **Tool-Loop**。
- **技术差距**: 缺少“显式计划 (Planning)”阶段。目前的 loop 模式在处理复杂逻辑（如跨 5 个文件重构）时，模型容易陷入局部工具调用而忘记全局目标。

### 2.2 代码编辑 (Code Editing)
- **业界方案**: **Aider 的 Search-Replace 块**被证明是目前最稳健的 LLM 代码编辑协议，它只传输变化部分，避免了全量重写带来的 Token 浪费和随机幻觉。
- **clude-code 现状**: 当前采用 `write_file` 全量覆盖。
- **演进结论**: 必须落地 **`apply_patch`**。这是从“玩具”转向“工程工具”的分水岭。

### 2.3 检索与召回 (Retrieval)
- **业界方案**: Cursor 使用专有向量库；Aider 使用 ctags 构建仓库图。
- **clude-code 现状**: 依赖简单的 `grep`。
- **技术差距**: 缺少“语义理解”。当用户说“修改登录逻辑”时，grep 无法自动关联到 `auth.py`，除非用户显式提及。

---

## 3. 技术选型结论 (Conclusion)

1.  **坚持“本地优先 (Local-first)”**: 对接 llama.cpp 是本项目的核心差异化。在隐私敏感场景下，不依赖云端 API 具有巨大价值。
2.  **强化“协议驱动 (Protocol-driven)”**: 业界大多是隐式 Prompt 约定，我们已有的 `schemas/` 是一项资产。通过 Pydantic 强校验参数，可以显著提升模型在小参数量下的执行成功率。
3.  **补齐“精确编辑 (Precision Editing)”**: 放弃全量写，转向 Patch 模式是接下来的最高优先级。

---

## 4. 演进路线建议 (Strategic Roadmap)

### 短期 (Phase 1: 稳健性)
- **精准编辑**: 实现基于语义块的 Patch 应用，解决长文件编辑崩溃问题。
- **鲁棒解析**: 针对 llama.cpp 容易输出额外文本的问题，增强 JSON 提取器。

### 中期 (Phase 2: 智能感知)
- **仓库图索引**: 即使不做向量检索，也应实现基于文件树和符号摘要的“上下文注入”。
- **自动化验证**: 引入 `Verification` 闭环。业界公认：没有自检的 Agent 产出代码不可靠。

### 长期 (Phase 3: 插件化)
- **工具扩展**: 完善 `docs/14` 中的插件协议，允许用户自定义本地 Bash 脚本作为工具。

