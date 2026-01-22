# Phase 2：更强验收项增强（Approval 可继续执行 + Plan 风险评估 + UI/CLI 运维）——实现思路

> 日期：2026-01-22  
> 背景：当前 Phase 2 已实现“生成审批单 + 本地 confirm 审批/拒绝 + PolicyEngine（可选）拦截”。  
> 但验收更强项需要补齐“后续审批继续执行”“更强风险评估”“更完整运维闭环”。

---

## 1. 现状与痛点（为什么要增强）

### 1.1 审批拒绝路径的问题
当前如果用户在 `confirm()` 阶段选择“不批准”，系统会把审批单写成 rejected 并立即返回。  
这会导致“稍后通过 CLI/管理员批准后继续执行”无法发生。

### 1.2 缺少“批准后继续执行”的闭环
审批通过后，系统缺少一个标准入口去继续执行已生成的 Plan（无需重新规划）。
验收要求：HIGH/CRITICAL 必须审批才能执行，但批准后应能继续推进任务。

### 1.3 风险贯穿还不够强
目前主要依赖 `IntentSpec.risk_level`。但业界更稳妥的做法是：
- 结合计划中工具的副作用（write/delete/exec/network）推导 plan risk
- 取 intent risk 与 plan risk 的最大值作为最终 risk（防止误配）

---

## 2. 增强目标（Strong Acceptance）

### 2.1 审批单保持 pending（允许后续批准）
- 用户在交互 confirm 中选择“不批准”时：
  - **不自动 reject**
  - 保持 pending 并返回“等待审批”的提示（含 approval_id）
  - 用户可通过 `clude approvals approve <id>` 或管理员系统进行审批

### 2.2 审批单保存 Plan 快照（可继续执行）
- ApprovalRequest 增加字段 `plan`（Plan 的最小 JSON 快照，包含 title/steps/status/tools_expected/verification_policy）
- 不保存 message history（避免泄露）

### 2.3 新增 CLI：`clude approvals run <id>`
- 前置条件：approval.status == approved
- 行为：加载 approval.plan，创建 AgentLoop，并直接进入“执行阶段”（跳过 planning）
- 提供 `--yes` 支持非交互自动确认（与现有 `chat --yes` 对齐）

### 2.4 Plan 风险评估器（MVP）
- 新增 `assess_plan_risk(plan)`：
  - 根据 steps.tools_expected 里出现的工具推导风险
  - 示例：`write_file/apply_patch/delete_file/run_cmd` 上浮为 HIGH/CRITICAL
- 最终风险：`max(intent_risk, plan_risk)`
- 审批门：final_risk in {HIGH, CRITICAL} → 必须审批

---

## 3. 代码改动点（Where）

### 3.1 ApprovalStore / ApprovalRequest
- 增加 `plan: dict | None`
- create() 接收 plan_json

### 3.2 AgentLoop 审批门
- 生成审批单时写入 plan 快照
- 用户 deny 时保持 pending，不写 rejected

### 3.3 CLI approvals
- 增加 `run` 子命令（approve 后继续执行）

### 3.4 风险评估器
- 新增 `src/clude_code/orchestrator/risk_assessor.py`
- AgentLoop 用它计算 plan_risk

---

## 4. 健壮性与边界
- approval.plan 缺失：`approvals run` 必须拒绝并给出明确错误（E_BAD_APPROVAL）
- plan JSON 校验失败：拒绝并提示（E_BAD_PLAN）
- `--yes` 仍会受 PolicyEngine/command_policy 拦截（安全优先）

---

## 5. 验收用例（强化版）
1) risk=HIGH 的 intent：生成 approval（pending），**不会执行工具**
2) 用户 deny confirm：approval 仍为 pending，可 CLI approve
3) CLI approve 后执行 `clude approvals run <id> --yes`：从 plan 继续执行
4) plan 包含 run_cmd 且 enterprise policy deny：执行被拦截并写审计


