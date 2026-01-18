# 09 | Git 工作流集成（可实现规格）(Git Workflow Spec)

> **Status (状态)**: Draft Spec (草案规格，后续结合 P2 落地)  
> **Audience (读者)**: Maintainers / Git Integration Owners (维护者/Git 集成负责人)  
> **Goal (目标)**: 定义 Agent 如何与版本控制系统协作，使其成为“Git 公民（Git-native/具备 Git 一等公民能力）”，产出整洁、有意义且符合团队规范的提交历史。

---

## 1. 核心动作 (Git Actions)

Agent 具备以下原子化 Git 能力：

- **变更摘要 (Diff)**: 总结自任务开始以来所有暂存/非暂存的改动。
- **自动提交 (Commit)**: 基于变更内容自动生成符合 [Conventional Commits](https://www.conventionalcommits.org/) 规范的消息。
- **状态感知 (Status)**: 确认工作区是否干净，防止覆盖用户正在手工修改的代码。
- **分支管理 (Branching)**: 针对复杂功能，建议在独立的特性分支上进行操作。

---

## 2. 自动化提交规范 (Commit Policy)

Agent 生成的提交消息应包含：
1. **类型**: `feat`, `fix`, `refactor`, `docs`, `test`。
2. **范围**: 修改涉及的主要模块。
3. **描述**: 简洁的中文概括（例如：`fix(auth): 修复登录时 Token 过期校验失效的问题`）。
4. **尾部**: 关联的 `trace_id` 或 `plan_id`，确保改动可追溯至 Agent 会话。

---

## 3. 安全防护与冲突 (Safety & Conflicts)

- **只读前置**: 在执行任何 Git 写入前，先执行 `git status`。
- **冲突中断**: 若检测到 `HEAD` 已在外部发生偏离（如用户刚拉取了最新代码），Agent 必须停止并提示用户手动同步。
- **大变更预警**: 涉及改动行数过大（如 > 500 行）或涉及敏感配置文件时，提交操作必须经由用户显式确认。

---

## 4. 相关文档（See Also / 参见）

- **工程路线图（Roadmap）**: [`docs/16-development-plan.md`](./16-development-plan.md)
- **工具协议与权限/沙箱（Tool Protocol）**: [`docs/02-tool-protocol.md`](./02-tool-protocol.md)
- **安全与策略（Security & Policy）**: [`docs/11-security-and-policy.md`](./11-security-and-policy.md)

---

---

## 5. 结论 (Conclusion/结论)

Git 是 Agent 与人类协作的“通用语言”。通过规范化的 Git 集成，Agent 不仅仅是修改了代码，更是将开发过程的思考产物以标准化的方式永久固化到了项目历史中。
