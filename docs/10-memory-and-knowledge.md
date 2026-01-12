# 10｜记忆与知识库（Memory & Knowledge）

目标：在不泄露隐私的前提下，让 agent 记住“用户偏好、仓库约定、长期上下文”，提升跨会话效率与一致性。

## 1. 记忆分层

### 1.1 短期记忆（Session Memory）
- **范围**：当前会话/当前任务
- **形态**：
  - 原始对话（有限轮数）
  - 会话摘要（每轮/每任务）
  - 工具调用摘要（结构化）
- **用途**：维持上下文连续性、避免重复搜索

### 1.2 中期记忆（Workspace Memory）
- **范围**：特定仓库
- **示例**：
  - 构建/测试命令
  - 代码风格约定（lint、formatter）
  - 常用入口文件与模块边界
- **存储**：`.clude/memory/workspace.json`（建议）

### 1.3 长期记忆（User/Org Memory）
- **范围**：用户偏好与组织规范（跨仓库）
- **示例**：
  - 输出语言、格式偏好
  - 安全策略偏好（是否允许网络）
  - 代码审查规范
- **注意**：必须可导出/可删除/可禁用

## 2. 数据模型（建议）

### 2.1 MemoryItem
- `id: string`
- `scope: session|workspace|user|org`
- `title: string`
- `content: string`（尽量短、可复用）
- `tags: string[]`
- `created_at: timestamp`
- `updated_at: timestamp`
- `source: user_explicit|inferred|imported`
- `sensitivity: public|internal|secret`

## 3. 写入策略（什么时候该记）

### 3.1 只在高信号时写入
- 用户明确要求“记住/保存”
- 仓库约定被多次验证（例如检测到 `pnpm` 且测试命令稳定）
- 输出偏好稳定（例如总是要求中文、总是要先给计划）

### 3.2 禁止自动写入的内容（默认）
- 密钥/令牌/密码
- 用户个人隐私
- 公司机密（除非企业策略允许且加密存储）

## 4. 读取与注入（如何用记忆）

### 4.1 检索策略
- 先取 workspace 记忆（与当前 repo 强相关）
- 再取 user/org 记忆（偏好与规范）
- 结合当前任务类型做过滤（tags）

### 4.2 注入方式
- 以“约束/偏好清单”形式进入 ContextPack：
  - “默认用 pnpm”
  - “测试命令：pnpm test”
  - “禁止访问网络”

## 5. 生命周期与治理

### 5.1 过期与更新
- 基于 `updated_at` 与命中次数
- 过期后不自动删除，但降权

### 5.2 可控性
- `memory list/search/delete`
- 一键关闭“自动推断记忆”
- 导出/导入（JSON）

## 6. 安全与隐私（必须对齐 `docs/11`）

### 6.1 脱敏与加密
- `secret` 级别默认拒绝写入
- 企业版可加密存储（本地密钥/OS keychain）

### 6.2 审计
- 任何记忆写入/删除都写审计日志

## 7. MVP 实现建议
- 先做：workspace 级“命令与约定”记忆（显式写入）
- 再做：用户偏好记忆（显式写入）
- 最后做：推断式记忆 + 评分/过期治理


