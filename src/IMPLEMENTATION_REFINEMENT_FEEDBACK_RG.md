# 工具稳健性增强：详细实现流程与思路 (Implementation Refinement)

本文件详细分析了 `tooling/feedback.py`、`rg 搜索` 以及 `doctor` 功能的实现思路、架构决策以及与业界的对齐策略。

---

## 1. 结构化摘要回喂 (tooling/feedback.py)

### 1.1 分析流程 (Analysis Flow)
1. **输入评估**：分析 LLM 在多轮对话中因 `Payload` 过大导致的“失焦”现象。
2. **信号提取**：定义每个工具对“决策”最有用的信号（例如：`run_cmd` 的 `exit_code` 是最高优先级信号，`output` 只是次级证据）。
3. **容量规划**：设定单次工具回馈的 Token 预算（约 2000-4000 字符），防止撑爆上下文。

### 1.2 实现思路 (Implementation Logic)
- **策略模式**：根据工具名分流。
- **关键技术 - Tail Sampling**：对于日志类输出，保留最后 N 行（通常错误信息都在末尾）。
- **关键技术 - Schema Mapping**：将 `ToolResult` 的庞大 JSON 映射为 `Summary` JSON。例如 `list_dir` 只返回文件计数和前 20 个项目名。

---

## 2. Ripgrep (rg) 集成与 Fallback

### 2.1 分析流程
1. **性能基准**：Python `rglob` 在处理包含 `node_modules` 或数万文件的项目时，耗时通常比 `rg` 慢 2~3 个数量级。
2. **兼容性降级**：考虑到用户环境的多样性，必须确保在没有 `rg` 的情况下功能依然可用。

### 2.2 实现思路
- **探测逻辑**：使用 `shutil.which("rg")` 进行非阻塞探测。
- **协议转换**：将 `rg --json` 的输出（Message-based）流式解析为我们的 `hits` 列表。
- **路径对齐**：统一以工作区根目录为基准输出相对路径，确保 LLM 能够直接使用该路径调用 `read_file`。

---

## 3. 环境诊断 (doctor) 增强

### 3.1 分析流程
1. **排障成本分析**：统计最常见的“Bug”来源，发现 40% 源于“环境依赖缺失”。
2. **引导式修复**：不仅要告诉用户“缺什么”，还要告诉用户“怎么补”。

### 3.2 实现思路
- **检测矩阵**：目前包含 Workspace 权限、LLM 连通性、二进制依赖（rg）。
- **平台感知建议**：根据 OS 建议不同的安装命令（conda/choco/scoop）。

---

## 4. 后续演进 (Roadmap)
- **语义压缩**：引入 LLM 对长工具输出进行自动总结（Summarize-then-Feedback）。
- **全局索引**：将 `rg` 的结果输入到 `Repo Map` 引擎中。

