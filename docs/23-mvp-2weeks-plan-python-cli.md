# 23｜两周 MVP 人天拆分（Python 纯 CLI + llama.cpp HTTP）

目标：Day1 起就能“真的在仓库里跑任务”，两周内交付一个可用的本地 code agent CLI：
- 能读/搜/改文件
- 能执行构建/测试命令（可控）
- 有最基础的策略确认与审计日志
- 有失败自救（重试/降级/停止）而非无限循环

## 0. 人天假设

- 1 人：10 个工作日（10 人天）
- 2 人：20 人天（并行）

以下拆分按“人天”估算，含开发 + 基础自测 + 文档。

## 1. 里程碑与验收标准

### M1（D1-D2）：LLM 连通 + 交互回合（2 人天）
- **工作**：
  - llama.cpp HTTP client（openai_compat + completion fallback）
  - CLI `chat` REPL
  - 最小系统提示词（工具 JSON 协议）
- **验收**：
  - `clude chat` 可对话
  - 能稳定返回中文回答（不崩溃、超时可提示）

### M2（D3-D5）：本地工具闭环（3 人天）
- **工作**：
  - 工具：`list_dir/read_file/grep/write_file/run_cmd`
  - workspace 路径边界（防越权）
  - 写/执行确认（默认开启）
  - 工具结果回喂模型，形成多轮工具调用链
- **验收**：
  - 让 agent 完成一个小任务：创建/修改一个文件并运行一个命令（用户确认后）
  - 工具调用失败能返回结构化错误，不死循环

### M3（D6-D7）：基础审计与可观测（2 人天）
- **工作**：
  - trace_id/session_id
  - 工具调用日志（JSON Lines）
  - 输出裁剪（命令输出/文件读取上限）
- **验收**：
  - 每轮会话产生一份可追溯日志（含工具调用与结果）
  - 大输出不炸内存、不刷屏

### M4（D8-D9）：验证闭环（lint/test/build）（2 人天）
- **工作**：
  - 项目探测（最小：package.json/pyproject/go.mod）
  - 验证策略：默认跑 `test` 或 `lint`（可配置）
  - 失败时给出结构化摘要（至少提取文件/行号/错误信息）
- **验收**：
  - 用户输入“修复某错误”，agent 能跑测试并将失败摘要喂回模型进行修复

### M5（D10）：打磨与发布（1 人天）
- **工作**：
  - README：如何启动 llama.cpp server、如何配置、常见问题
  - `doctor`（最小）：检查 base_url 连通、workspace 可读写、rg 是否存在（可选）
- **验收**：
  - 新机器按 README 10 分钟内跑起来

## 2. 并行排期（2 人版本）

### 工程师 A（偏编排/LLM）
- D1-D2：LLM client + agent loop 守卫（最大工具调用次数、重试）
- D3-D5：工具协议强化（更严格 JSON 解析、坏输出重试）
- D6-D7：审计日志 + replay 雏形

### 工程师 B（偏工具/验证）
- D1-D2：LocalTools（读/搜/写/命令）+ 路径边界
- D3-D5：Verification（探测 + 运行 + 输出裁剪）
- D6-D7：doctor + 文档 + UX 打磨

## 3. 风险与兜底

- **模型不稳定输出工具 JSON**：增加“格式守卫重试”（最多 2 次）+ 降温 + 更强 system prompt
- **llama.cpp 接口不一致**：openai_compat 失败自动提示切换 completion 模式
- **执行命令风险**：默认确认 + allowlist（后续 v1）


