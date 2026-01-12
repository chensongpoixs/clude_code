# 09｜Git 工作流（Diff / Commit / Branch / PR）（可选但强烈建议）

目标：把“代码改动”变成可合并的工程产物：可审查、可回滚、可追踪。

## 1. 子模块拆分

### 1.1 Git Adapter（底层封装）
- **职责**：封装 git 命令，返回结构化结果
- **接口建议**：
  - `git.status()`
  - `git.diff(paths?)`
  - `git.create_branch(name)`
  - `git.commit(message)`
  - `git.log(limit)`
  - `git.restore(paths?)`（回滚未提交改动）
- **安全要点**：所有命令经 Policy Engine 过滤；默认禁止 `push`。

### 1.2 Change Summarizer（变更总结器）
- **输入**：diff + Plan + 验证结果
- **输出**：
  - 用户可读总结（What/Why/How verified）
  - commit message（conventional commits 可选）
  - PR 描述（模板化）

### 1.3 Review Helper（审查辅助，可选）
- **能力**：
  - 按文件/功能点拆分 diff
  - 标注风险点（安全、性能、兼容）
  - 生成测试建议与回滚方案

## 2. Git 流程（推荐默认）

### 2.1 分支策略
- 每个任务默认新建分支：`agent/<date>-<short>`（可配置）
- 任务结束输出：
  - `git status`
  - `git diff --stat`
  - 本地验证结果

### 2.2 提交策略
- 小步提交：每 1~3 个步骤一个 commit（可审查）
- commit message 模板（示例）：
  - `fix(auth): handle token refresh failure`
  - `feat(ui): add settings toggle for ...`

### 2.3 PR（可选）
- 生成 PR 描述（不自动创建远端 PR，除非用户显式确认 + 配置 token）
- 描述包含：
  - 背景/问题
  - 改动点列表
  - 验证方式（命令与结果）
  - 风险与回滚

## 3. 危险操作控制

### 3.1 默认禁止
- `git push`
- 修改 `.git/config`、hooks（除非允许）

### 3.2 必须确认
- 重写历史（rebase --interactive、reset --hard）
- 强推（force push）

## 4. MVP 实现建议
- 先做：`status/diff/commit/branch/restore`
- 再做：PR 文案生成
- 最后做：与平台集成（GitHub/GitLab）+ 评论/审查建议（企业版）


