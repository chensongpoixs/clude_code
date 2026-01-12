# clude-code 详细开发任务表 (ROADMAP)

本文件用于追踪每个具体功能的实现状态。

## P0: 核心稳定性
- [x] **LLM 输出解析增强**: 支持模型在 JSON 前后输出解释文字，自动提取 JSON。
- [ ] **工具参数 Schema 校验**: 调用工具前强制检查参数格式。
- [ ] **原子化文件写入**: 使用临时文件和 rename 确保 IO 安全。
- [x] **可观测执行轨迹**: `clude chat --debug` 输出每步轨迹，并写入 `.clude/logs/trace.jsonl`。
- [x] **人格硬化与执行加固**: 强化 Prompt 确保 Agent 自主性，并实现吐字防抖与 CoT 剥离。
- [x] **结构化工具回馈与采样**: 落地 `tooling/feedback.py` 逻辑，支持语义逻辑锚点采样。

## P1: 代码编辑与控制
- [x] **实现 `apply_patch` 工具**: MVP 采用 old/new block 替换 + 唯一性保护 + 模糊匹配。
- [x] **实现 `undo_patch` 能力**: 记录每次修改的备份与 before/after hash，支持基于 undo_id 回滚（含冲突检测/force）。
- [ ] **敏感信息过滤**: 在审计日志和发送给 LLM 的上下文中自动遮蔽 API Key。
- [x] **Ripgrep 替换 Python grep**: 优先使用 `rg --json` 获取稳定/高性能搜索结果，缺失时降级。

 ## P2: 任务规划与验证
 - [ ] **Plan 阶段引入**: 模型先给出执行步骤，由用户整体确认。
 - [ ] **自动化测试集成**: 识别 `pytest` 等测试框架，修改后自动运行并反馈。
 - [x] **交互式环境修复**: `clude doctor --fix` 可自动安装缺失的 rg、ctags 等。
 - [x] **全量 Vector RAG**: 实现 LanceDB 后台异步全量索引与语义搜索工具。
 - [x] **Context 窗口管理**: 已实现滑动窗口历史裁剪、CoT 剥离及结构化工具采样，防止 Token 溢出。

 ## P3: 高级能力
 - [ ] **Git 分支/Commit 自动化**: 深度集成 Git 工作流。
 - [x] **LSP 符号跳转集成**: 已通过 ctags 实现 Repo Map，辅助模型精准定位函数定义。
 - [ ] **GUI/Web 界面预览**: (可选)

