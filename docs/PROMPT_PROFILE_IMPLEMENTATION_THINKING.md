# Prompt Profile（按意图选择 System/User Prompt）落地方案（实现思路）

> 来源：`agent_design_v_1.0.md` 第 2~6 章（Prompt Profile / Registry / Selector / Orchestrator 伪代码）

---

## 1. 需求对齐（必须满足）

### 1.1 Prompt Profile 定义
- Prompt Profile = **System Prompt 组合** + **User Prompt 模板**
- 目标：不同意图使用不同 Prompt Profile，确保行为可控、可治理、可审计。

### 1.2 关键约束
- **Intent 不直接引用 prompt 文件**，只引用 `prompt_profile` 名称（平台级配置）。
- **System Prompt 只能收紧权限**（不可放权）。
- **禁止直接使用原始用户输入作为最终 user prompt**：必须经 user 模板结构化。

---

## 2. 与当前代码的关系（现状与缺口）

### 2.1 当前已有能力（可复用）
- Intent Registry：`src/clude_code/orchestrator/registry/*`
  - `IntentRouter` 能从 user_text 路由到某个 intent（规则优先）。
- Prompt 资产化：`src/clude_code/prompts/` + `PromptManager`
  - 已支持“按 stage 的三层（base/domain/task）组合 + SemVer + front matter”。
- AgentLoop 的 stage prompt 选择：`AgentLoop._compose_stage_prompt(stage=...)`
  - 当前 stage 覆盖：system/planning/execute_step/replan/...

### 2.2 当前缺口（本次补齐）
- **没有 Prompt Profile Registry**（`prompt_profiles.yaml`）这个中间层。
- **system prompt 在 __init__ 固化**：无法随“每轮意图”动态切换。
- **没有 user prompt 模板 stage**：run_turn 仍会直接使用 raw user_text 或 planning_prompt。

---

## 3. 设计落地（MVP）

### 3.1 新增配置：Prompt Profile Registry
- 新增文件：`.clude/registry/prompt_profiles.yaml`（可选，不存在则仅使用默认 profile）
- 配置结构（MVP，兼容现有 StagePrompts 机制）：
  - `prompt_profiles: { <name>: { description, risk_level?, prompts: { system, user_prompt } } }`
  - 其中 `prompts.system` 与 `prompts.user_prompt` 都是 `PromptStage(base/domain/task)` 三层引用

> 说明：为最小改动复用当前 PromptManager/StagePrompts，不引入 `system_prompts: [a,b,c]` 的全新渲染引擎。

### 3.2 Intent 绑定 Profile（新增字段）
- 在 `IntentSpec` 增加 `prompt_profile: Optional[str]`
- 运行时优先级（同一 stage 的 triplet 选择）：
  - **Intent.prompts.stage（三层） > PromptProfile.prompts.stage（三层） > Project.prompts.stage > 默认**
- 兼容策略：
  - 如果 intent 没配置 `prompt_profile`：保持现有行为（兼容老配置）
  - 如果配置了 `prompt_profile`，但 profile 不存在：记录 warning 并回退默认

### 3.3 AgentLoop 注入点

#### A) 动态 system prompt（按意图每轮刷新）
- run_turn 完成意图路由后，调用 `_refresh_system_prompt_for_intent()`：
  - 使用 stage=`system` 的三层组合（可能来自 profile）
  - 变量仍包含工具清单/项目记忆/env_info/repo_map（保持当前工程行为一致）
  - 更新 `messages[0]` 的 system content（确保后续 LLM 调用生效）

#### B) user prompt 模板（结构化 user 输入）
- 新增 stage=`user_prompt`：
  - vars：`user_text`, `planning_prompt`, `project_id`, `intent_name`, `risk_level`
- run_turn 中改为：
  - `user_content = render(user_prompt)`（禁止直接用 raw user_text）
  - 若模板为空/缺失：回退到旧逻辑（planning_prompt 或 raw user_text）

---

## 4. Prompt 资产（MVP）

### 4.1 新增默认 user_prompt 模板
- `src/clude_code/prompts/user/query.j2`（默认 user_prompt 模板，当前版本）
- 支持：
  - 使用结构化字段包装 raw user_text（禁止直接拼 raw）
  - 若 planning 开启，`AgentLoop` 会在变量里提供 `planning_prompt`，模板可选择性包含（推荐直接在模板中引用）

---

## 5. 可观测性与健壮性

### 5.1 审计与事件
- 建议事件（MVP 至少写 logger/trace）：
  - `prompt_profile_selected`：profile/name + stage refs
  - `system_prompt_refreshed`：intent/profile + content_len

### 5.2 健壮性边界
- `prompt_profiles.yaml` 不存在：不崩，回退默认 stage prompts
- profile 名不存在：不崩，回退默认
- prompt 文件缺失：PromptManager 已降级为空文本，调用方回退旧逻辑


