# Phase 3：沙箱预演与事务回滚（Sandbox + Transaction Rollback）——实现思路

> 日期：2026-01-22  
> 对齐文档：`docs/AGENT_DESIGN_ENTERPRISE_FEASIBILITY_REPORT.md` Phase 3（L173-L179）

---

## 1. Phase 3 目标（对齐验收）

### 交付项
- SandboxRunner（git worktree 优先，fallback temp copy）
- 事务边界：失败自动回滚，成功合并

### 验收
- CRITICAL 任务默认沙箱执行
- 可一键回滚，不污染主 workspace

---

## 2. 总体策略（MVP → 可运营）

### 2.1 MVP 先做“安全不污染”
- **默认 CRITICAL**：在沙箱目录执行工具/写文件/跑命令
- 主 workspace 不做任何写操作
- 沙箱执行完成后：
  - 验证通过：合并回主 workspace
  - 验证失败或异常：丢弃沙箱目录（回滚）

### 2.2 优先级：git worktree > temp copy

#### A) git worktree（优先）
- 条件：
  - workspace 是 git 仓库
  - git 可用
- 做法：
  - `git worktree add <sandbox_dir> -b clude_sandbox_<id> <base_ref>`
  - 在 worktree 内执行 plan
  - 完成后：
    - 通过验证：生成 diff 并应用到主 workspace（`git diff` + apply 或逐文件覆盖）
    - 移除 worktree：`git worktree remove <sandbox_dir>`，必要时 `git branch -D ...`

#### B) temp copy（fallback）
- 条件：非 git 仓库 / git 不可用 / worktree 失败
- 做法：
  - 复制 workspace 到 `<tmp>/clude_sandbox_<id>`（可忽略 `.git/`, `.clude/`, `node_modules/` 等）
  - 在拷贝中执行 plan
  - 完成后：
    - 通过验证：计算变更文件集合并回写到主 workspace
    - 失败：直接删除 temp 目录（主 workspace 无污染）

---

## 3. 事务边界与合并策略（MVP）

### 3.1 事务边界
- transaction_id = `sandbox_id`
- 边界内：只允许修改沙箱目录

### 3.2 合并策略（先做最小可用）
- 方案 1（git 仓库优先）：`git diff` 生成 patch，然后在主 workspace `git apply`（或 `apply_patch` 工具回放）
- 方案 2（通用 fallback）：记录沙箱中被修改的文件路径列表（已有 `_turn_modified_paths`），把这些文件从沙箱复制回主 workspace（严格限制在 workspace 内）

> MVP 选择：优先走“复制已修改文件回主 workspace”，因为更跨平台、更少依赖外部工具。

---

## 4. 风险与降级

- git 不可用 / worktree 失败：降级 temp copy
- 沙箱复制过大：允许配置 ignore_dirs + 最大复制文件数（后续）
- 合并冲突：MVP 直接拒绝合并并提示用户手工处理（避免 silent corruption）

---

## 5. 审计与可观测性

审计事件建议：
- `sandbox_created`（type=worktree|copy, path=...）
- `sandbox_execute_started/ended`
- `sandbox_merge_applied`（files=n）
- `sandbox_discarded`（reason=...）

---

## 6. 验收用例（最小）

1) final_risk=CRITICAL：所有写操作只发生在沙箱目录  
2) 沙箱执行失败：主 workspace 不变（回滚成功）  
3) 沙箱执行成功：仅把变更文件合并回主 workspace


