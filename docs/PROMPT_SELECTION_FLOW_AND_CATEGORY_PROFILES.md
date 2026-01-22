# Prompt 选择流程（按意图）与五类意图 Prompt 覆盖情况（分析 + 完善方案）

> 对齐：`src/clude_code/orchestrator/classifier.py` 的五类意图（CODING_TASK / CAPABILITY_QUERY / REPO_ANALYSIS / GENERAL_CHAT / UNCERTAIN）
> 目标：解释“现在代码如何按用户输入意图选择 system/user 提示词”，并检查是否已经为这五类意图配置了不同系统提示词和用户提示词；若未完善给出补齐方案与实现点。

---

## 1. 当前系统的 Prompt 目录结构（已对齐最新设计）

目录位于：`src/clude_code/prompts/`

- `system/`
  - `system/core/`：全局规范/安全边界（Core）
  - `system/role/`：角色能力与约束（Role）
  - `system/policy/`：风险/合规/权限约束（Policy）
  - `system/context/`：运行期上下文注入（工具清单/项目记忆/环境信息）（Context）
- `user/`
  - 结构化 user 输入模板（query/coding_task/repo_analysis/...）
  - 以及规划/执行/重规划等 stage 的 user prompt（planning/execute_step/replan/...）

---

## 2. 当前代码的“按意图选择 Prompt”的真实执行流程（AgentLoop）

入口：`src/clude_code/orchestrator/agent_loop/agent_loop.py::AgentLoop.run_turn`

### 2.1 关键步骤（按顺序）
1) **提取关键词**：用于 UI 展示与语义检索窗口（不影响 prompt 选择）

2) **意图分类（5 类）**：
- 调用 `IntentClassifier`（LLM 分类器）
- 输出类别来自：`classifier.py` 的 5 类（CODING_TASK / CAPABILITY_QUERY / REPO_ANALYSIS / GENERAL_CHAT / UNCERTAIN）
- 作用：当前主要用于 “是否启用 planning” 的决策门（enable_planning）

3) **Intent Registry 路由（规则优先）**：
- `IntentRouter.route()` 用 registry keywords 进行匹配（精确/模糊）
- 找到 `IntentSpec` 则形成 `IntentMatch`（包含 tools/risk/prompts/prompt_profile 等）

4) **Prompt Profile 选择（中间层）**：
- 若 IntentSpec 配置了 `prompt_profile`：
  - system/user_prompt 等 stage 的三层 refs 会优先来自 Prompt Profile
- 若 intent 没配置或没命中：
  - 走默认 stage prompts（或者 project/prompts 覆盖）

5) **刷新 system prompt（本轮生效）**：
- `run_turn` 在路由后调用 `_refresh_system_prompt_for_current_intent()`
- 本质是重新 compose stage=`system`，并更新 `messages[0]`（system message）

6) **渲染 user prompt（本轮发送给 LLM 的 user_content）**：
- `run_turn` 构造 `user_content`：
  - planning 开启时：planning_prompt 走 stage=`planning`
  - user 输入包装走 stage=`user_prompt`（结构化输入）

> 注意：本仓库的“planning/execute_step/replan”等都是通过 **user 消息**把阶段指令发给模型，因此它们归类到 `prompts/user/*`。

---

## 3. 五类意图是否已配置“不同 system/user prompts”？

### 3.1 结论（当前状态）
- 目前 **没有**对 `classifier.py` 的 5 类意图提供“完整的、互相区分的 system/user prompts”覆盖。
- 现状是：
  - system：默认 system/core/global + system/role/developer + system/context/runtime
  - user_prompt：默认 user/query
  - 只有当某个 intent 显式配置了 `prompt_profile`，才会切换到 profile 指定的 system/user_prompt
- 这意味着：仅靠“5 类分类结果”本身，无法自动切到不同 system/user prompts（除非额外映射）。

---

## 4. 完善方案（让 5 类分类结果能自动选择不同 system/user prompts）

### 4.1 目标
当 registry 未命中或 intent 未配置 `prompt_profile` 时：
- 仍能基于分类结果（5 类）选到一个默认 profile：
  - CODING_TASK → `classifier_coding_task`
  - REPO_ANALYSIS → `classifier_repo_analysis`
  - CAPABILITY_QUERY → `classifier_capability_query`
  - GENERAL_CHAT → `classifier_general_chat`
  - UNCERTAIN → `classifier_uncertain`

### 4.2 落地点
1) AgentLoop 在 `_classify_intent_and_decide_planning()` 里保存分类结果（例如 `self._last_intent_category`）
2) `_resolve_stage_prompt_triplet()` 在 intent 未指定 prompt_profile 时，按 `self._last_intent_category` 选择 profile
3) 增加 profile 示例与对应 prompt 文件：
   - system/role/analyst.md / system/role/operator.md（用于不同类别）
   - user/coding_task.j2 / user/repo_analysis.j2 / user/capability_query.j2 / user/general_chat.j2

### 4.3 验收
- 同一 project 下，输入“写代码”与“你能干嘛”触发不同 profile，system/user_prompt 内容不同
- 不配置 `prompt_profiles.yaml` 时不崩溃，回退默认


