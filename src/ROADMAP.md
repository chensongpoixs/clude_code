# clude-code 详细开发任务表 (ROADMAP)

本文件用于追踪每个具体功能的实现状态。

## P0: 核心稳定性
- [x] **LLM 输出解析增强**: 支持模型在 JSON 前后输出解释文字，自动提取 JSON。
- [ ] **工具参数 Schema 校验**: 调用工具前强制检查参数格式。
- [ ] **原子化文件写入**: 使用临时文件和 rename 确保 IO 安全。
- [x] **可观测执行轨迹**: `clude chat --debug` 输出每步轨迹，并写入 `.clude/logs/trace.jsonl`。

## P1: 代码编辑与控制
- [x] **实现 `apply_patch` 工具**: MVP 采用 old/new block 替换 + 唯一性保护（expected_replacements）。
- [x] **实现 `undo_patch` 能力**: 记录每次修改的备份与 before/after hash，支持基于 undo_id 回滚（含冲突检测/force）。
- [ ] **敏感信息过滤**: 在审计日志和发送给 LLM 的上下文中自动遮蔽 API Key。

## P2: 任务规划与验证
- [ ] **Plan 阶段引入**: 模型先给出执行步骤，由用户整体确认。
- [ ] **自动化测试集成**: 识别 `pytest` 等测试框架，修改后自动运行并反馈。
- [ ] **Context 窗口管理**: 实现滑动窗口或摘要机制，防止长会话超出 Token 限制。

## P3: 高级能力
- [ ] **Git 分支/Commit 自动化**: 深度集成 Git 工作流。
- [ ] **LSP 符号跳转集成**: 辅助模型更精准地找到函数定义。
- [ ] **GUI/Web 界面预览**: (可选)

