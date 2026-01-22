# Phase 2：审批流与高风险治理（Risk + Approval + PolicyEngine）——实现思路

> 日期：2026-01-22  
> 对齐文档：`docs/AGENT_DESIGN_ENTERPRISE_FEASIBILITY_REPORT.md` Phase 2（L164-L172）

---

## 1. Phase 2 目标（对齐验收）

### 交付项
- risk_level 贯穿（intent → plan → tool）
- `WAITING_FOR_APPROVAL` 状态、`ApprovalStore`、UI 面板
- `PolicyEngine` 接入工具生命周期（RBAC + 路径/命令规则）

### 验收
- HIGH/CRITICAL 任务必须审批才能执行
- 审批与拒绝均可追溯（audit 事件齐全）

---

## 2. 设计原则

- **最小闭环优先**：先保证“可拦截/可审批/可追溯/可恢复”，再做体验增强（队列/多角色/远程审批）。
- **不破坏现有交互**：已有 `confirm()` 仍可用于“本地快速审批”，但审批必须落盘到 ApprovalStore，满足审计。
- **默认安全**：未配置企业策略时，不阻塞主流程；配置策略后严格生效。

---

## 3. 风险贯穿（Risk Propagation）

### 3.1 风险来源
- `IntentSpec.risk_level`（意图注册表给出的风险等级，Phase 2 的主判据）
- 工具 side_effects 与工具类型（write/exec/delete）作为辅助手段（后续可升级为“计划级风险评估器”）

### 3.2 风险策略（MVP）
- `LOW/MEDIUM`：按现有 confirm_write/confirm_exec 走交互确认
- `HIGH/CRITICAL`：必须进入审批流（ApprovalStore），没有审批就阻塞执行

---

## 4. 审批流（Approval Flow）

### 4.1 状态机
新增状态：`WAITING_FOR_APPROVAL`

典型路径：
- `PLANNING` →（生成 plan）→ `WAITING_FOR_APPROVAL` →（审批通过）→ `EXECUTING`
- `WAITING_FOR_APPROVAL` →（审批拒绝）→ `DONE`（或 BLOCKED，视产品策略）

### 4.2 ApprovalStore（文件存储，按 project 隔离）

- 存储位置：`ProjectPaths(...).approvals_dir()`（按 `project_id` 隔离）
- 文件：`approvals/{approval_id}.json`
- 字段（最小集）：
  - `id`, `project_id`, `trace_id`, `risk_level`, `intent_name`
  - `status`: pending/approved/rejected
  - `requested_at`, `decided_at`, `decided_by`, `comment`
  - `plan_summary`（短摘要，避免泄露敏感信息）

### 4.3 触发点（MVP）
- 在 planning 成功生成 Plan 后：
  - 若 intent.risk_level ∈ {HIGH, CRITICAL}：
    - 生成 approval request
    - 事件：`approval_required`
    - 审计：`approval_required`
    - 进入 `WAITING_FOR_APPROVAL`
    - 返回提示：告诉用户如何 `clude approvals approve <id>` 或在交互 confirm 中批准

---

## 5. PolicyEngine 接入 Tool Lifecycle（RBAC + 路径/命令）

### 5.1 检查点（MVP）
- `read_file`：`check_file_access(path, read)`
- `write_file/apply_patch/undo_patch`：`check_file_access(path, write)`
- `delete_file`：`check_file_access(path, delete)`
- `run_cmd`：`check_command(command)`

### 5.2 审计事件
- `policy_deny_file` / `policy_deny_cmd`（含 reason、missing_permissions）
- `policy_allow_*` 可选（默认不刷屏，仅审计 deny）

### 5.3 用户选择
- 先引入最小配置（默认用户 `default`），后续可从 CLI/环境变量传入 user_id。

---

## 6. CLI 与 UI（可运营）

### 6.1 CLI：`clude approvals`
- `list`：列出 pending
- `approve <id>`：写入 approved
- `reject <id>`：写入 rejected

### 6.2 UI（OpencodeTUI）
- 监听 `approval_required` / `approval_status_changed`
- 操作面板展示 `审批: pending/approved/rejected (id=...)`

---

## 7. 健壮性与边界

- 无 `intents.yaml` / 无 policy 配置时：默认不触发审批，不阻塞。
- 审批文件读写失败：必须降级为“阻塞并提示用户”，并写入 audit/trace，避免静默绕过。
- 避免泄露：approval 的 `plan_summary` 只存短摘要，不存完整消息历史。

---

## 8. 验收用例（最小）

1) risk=HIGH 的 intent：生成 plan 后进入 WAITING_FOR_APPROVAL，不会执行任何工具  
2) `clude approvals approve <id>` 后再继续执行：允许执行工具  
3) PolicyEngine deny：工具被拦截，返回 E_POLICY，并写审计


