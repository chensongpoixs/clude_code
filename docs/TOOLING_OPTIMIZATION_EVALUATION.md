# 工具模块优化点评估与分析报告

> **评估日期**: 2026-01-23  
> **评估范围**: Phase 1-6 已实现功能 + 待落地优化点

---

## 1. 总体评估摘要

当前的优化路径高度对齐了 **Claude Code** 与 **Cursor** 的工业界实践。通过“分发层统一管控”、“回喂摘要压缩”以及“流式 I/O”，显著提升了 Agent 在处理大型代码仓库时的稳定性。

---

## 2. 详细评估表

| 模块/优化点 | 是否合理 | 业界对标 | 核心收益 | 存在问题/风险点 | 改进建议 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Grep --vimgrep** | ✅ 非常合理 | VS Code / Vim | Token 节省 ~75% | 部分复杂正则在 `rg` 和 Python 引擎间行为不完全一致。 | 统一使用 `ripgrep` 语法规范，文档中明确正则方言。 |
| **ReadFile 流式采样** | ✅ 合理 | Claude Code | 内存节省 80%+ | 头尾采样可能漏掉中间的关键报错信息。 | 结合回喂层的“关键词窗口采样”，确保“读”与“看”的信息互补。 |
| **RunCmd 安全优化** | ✅ 合理 | 业界安全规范 | 防注入 / 跨平台 | Windows 下简单 split 容易破坏带引号的参数。 | 引入 `shlex.split` 的 Windows 模拟实现或强制要求模型传数组参数。 |
| **ListDir 分页排序** | ✅ 合理 | GitHub 目录树 | 降噪 / Token 优化 | 如果核心文件在分页后（如第 101 个），模型可能漏掉。 | 默认排序应考虑 `ctags` 权重或 Git 修改频率，而非单纯字母序。 |
| **GlobSearch 深度限制** | ✅ 合理 | IDE 检索性能 | 防止大项目 IO 阻塞 | 深度限制可能导致模型找不到深层嵌套的文件。 | 当因深度截断时，在 warning 中提示模型尝试更精准的 `target_directory`。 |
| **会话级缓存 (Cache)** | ✅ 已优化 | Cursor | 0 Token 重复开销 | ~~写操作后 `clear()` 过于保守~~ | **P0-1 已完成**: 实现 `invalidate_path()` 细粒度失效 |
| **Question 阻塞协议** | ✅ 已优化 | 人机协作 (HITL) | 澄清需求 / 安全 | ~~当前实现为非阻塞~~ | **P0-2 已完成**: 添加 `is_waiting_input()` / `answer_question()` API |
| **TodoManager 更新协议** | ✅ 已优化 | 任务状态机 | 执行有序性 | ~~使用 `update:` 暗号协议~~ | **P1-2 已完成**: 添加显式 `todo_id` 参数 |
| **TaskAgent 异步执行** | ✅ 已优化 | 子 Agent 架构 | 复杂任务拆解 | ~~使用 `asyncio.run` 嵌套~~ | **P1-1 已完成**: 同步化，移除 asyncio 依赖 |

---

## 3. 核心问题深度分析

### 3.1 缓存失效的“原子性”与“细粒度” (P0)
目前 `dispatch_tool` 在执行 `write_file` 或 `apply_patch` 成功后直接调用 `cache.clear()`。
- **优点**: 绝对安全，不会返回脏数据。
- **缺点**: 性能波动大。如果模型在编辑 A 文件后想读 B 文件，原本命中的缓存会丢失。
- **建议**: `ToolResultCache` 增加 `invalidate_path(path)`，只删除 key 中包含该路径的项。

### 3.2 Question 工具的“假死”现象
现在的 `ask_question` 只是返回了一个 JSON。如果 Orchestrator 不拦截这个结果并进入等待输入态，模型会看到“提问成功”的回喂，然后由于没收到答案而继续基于错误假设进行推理。
- **建议**: 修改 `AgentLoop`，当工具返回 `type: "question"` 时，中断当前 turn，将状态设为 `WAITING_USER`。

### 3.3 Repo Map 的 Token 挤压
虽然 `repo_map` 做了 Top 50 限制，但在超小模型（如 8k 窗口）中依然过大。
- **建议**: `generate_repo_map` 应接受 `token_budget` 参数，由分发层根据当前上下文余量动态计算。

---

## 4. 已完成的优化 (2026-01-23)

### 4.1 代码层面
- [x] **P0-1**: `ToolResultCache.invalidate_path` 细粒度失效 → 支持 3 种匹配策略
- [x] **P0-2**: Question 工具阻塞协议 → 添加 `is_waiting_input()` / `answer_question()` API
- [x] **P1-1**: TaskAgent 同步化 → 移除 `asyncio.run()` 嵌套
- [x] **P1-2**: TodoManager 显式 ID 协议 → 移除 `"update:"` 暗号，添加 `todo_id` 参数

### 4.2 文档层面
- [x] 在 `docs/TOOLING_INDUSTRY_OPT_tool_read_file.md` 中增加"二进制文件处理"规范
- [x] 在 `docs/TOOLING_INDUSTRY_OPT_CORE_CACHE.md` 中补充"写后失效"的技术原理

### 4.3 实施文档
- `docs/IMPL_P0_1_CACHE_INVALIDATE_PATH.md` - 缓存细粒度失效
- `docs/IMPL_P0_2_QUESTION_BLOCKING.md` - Question 阻塞协议
- `docs/IMPL_P1_1_TASKAGENT_ASYNC_FIX.md` - TaskAgent 同步化
- `docs/IMPL_P1_2_TODOWRITE_PROTOCOL.md` - TodoManager 显式 ID

