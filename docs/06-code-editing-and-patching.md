# 06 | 代码编辑与补丁系统（可实现规格）(Editing & Patching Spec)

> **Status (状态)**: Stable Spec (稳定规格，可直接落地实现)  
> **Audience (读者)**: Maintainers / Patch Engine Owners (维护者/补丁引擎负责人)  
> **Goal (目标)**: 让“写文件/改代码”变成可控（Controllable/可控）、可回滚（Rollbackable/可回滚）、冲突可处理（Conflict-Resolvable/可处理冲突）的工程动作，而不是随意覆盖文件。

## 1. 编辑策略（优先级）

1. **最小变更**：先改最小范围以通过验证
2. **局部修改优先**：优先 `apply_patch`（基于上下文定位），避免整文件重写
3. **保留风格一致**：沿用现有缩进、命名、导入顺序、项目规范
4. **每次修改可解释**：输出“为什么改、改了哪里、如何验证”

## 2. 补丁格式与应用

### 2.1 推荐补丁格式（统一入口）
- 使用“带上下文的 diff/patch”：
  - 通过上下文行定位，避免行号漂移
  - 应用失败时能给出冲突位置

### 2.2 Patch 预检（Preflight）
在真正写入前，必须执行：
- 目标文件存在性检查
- 上下文片段匹配检查（防止错改）
- 变更影响评估：
  - 改动行数
  - 是否跨越多文件
  - 是否涉及敏感目录（触发确认）

### 2.3 冲突处理（Conflict Resolution）
- 场景：文件已变化、上下文不匹配
- 处理顺序：
  1. 重新读取目标文件片段
  2. 生成新的 patch（基于最新内容）
  3. 若仍失败：提示用户手动介入，并给出冲突片段

## 3. 原子写与备份

### 3.1 原子写（强烈建议）
- 写临时文件 → 校验 → rename 覆盖
- 记录：
  - old_hash/new_hash（旧哈希/新哈希）
  - patch 内容（补丁内容）

### 3.2 备份与撤销
- 每次写操作保存 `undo_patch`
- 任务级撤销：按 `plan_id` 汇总所有 patch，支持“一键回滚”

## 4. 变更可视化（面向用户）

### 4.1 变更摘要
- 文件列表
- 每个文件改动行数
- 关键片段 before/after（只展示最关键）

### 4.2 危险变更提示
触发“必须确认”的例子：
- 删除文件
- 改动 > N 个文件（默认 20）
- 改动敏感路径：`.github/workflows/`、`infra/`、`auth/`、`payments/`

## 5. 格式化与 import 整理（可选）

建议通过工具化实现，而不是模型“手改”：
- `prettier`/`eslint --fix`
- `gofmt`
- `black`/`ruff format`

## 6. MVP 实现建议
- 先做：`apply_patch` + 失败重试 + undo_patch
- 再做：冲突自动重基（rebase-like）
- 最后做：语法树级编辑（AST-based editing）提升稳健性

---

## 7. 相关文档（See Also / 参见）

- **工具协议（Tool Protocol）**: [`docs/02-tool-protocol.md`](./02-tool-protocol.md)
- **计划分解与任务执行（Planning）**: [`docs/05-planning-and-tasking.md`](./05-planning-and-tasking.md)
- **Lint/Test/Build（验证闭环）**: [`docs/08-lint-test-build.md`](./08-lint-test-build.md)


