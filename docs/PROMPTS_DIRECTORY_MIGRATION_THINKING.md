# 提示词目录结构迁移（按最新设计文档）——思考过程与落地方案

> 对齐来源：`agent_design_v_1.0.md` 第 3.3 节目录结构（system/core|role|policy|context + user/*）

---

## 1. 为什么要迁移

当前仓库提示词目录为 `prompts/base|domains|tasks`，是“三层继承”工程化结构；但最新设计文档要求提示词资产按职责拆分为：
- `prompts/system/`：系统提示词资产（Core/Role/Policy/Context）
- `prompts/user/`：用户提示词模板（query/code_generate/prod_action 等）

迁移目标：
- 让“Prompt Profile = system_prompts 组合 + user_prompt_template”的配置与目录结构天然一致；
- 让代码实现（AgentLoop/Profile Selector）引用路径与文档一致，降低维护成本；
- 避免把不支持的模板语法（如 Jinja `{% %}`）原样发送给 LLM。

---

## 2. 目录映射策略（从旧到新）

### 2.1 system prompts 映射
- 旧 `base/security.md` → 新 `system/core/global.md`
  - 核心安全边界、抗注入、通用输出规则：属于 Core。
- 旧 `domains/agent_loop.md` → 新 `system/role/developer.md`
  - “你处于 AgentLoop 可调用工具环境/控制协议”更像角色能力约束：属于 Role。
- 旧 `tasks/system_prompt.j2` → 新 `system/context/runtime.j2`
  - 工具清单、项目记忆、env_info、repo_map 属于运行期上下文注入：属于 Context。

> Policy（readonly/high_risk/prod_guard）在现有仓库中主要通过审批/PolicyEngine 实现，MVP 先提供 `system/policy/readonly.md`、`system/policy/high_risk.md` 两个占位文件用于 Profile 组合（内容可从 Core 里再细化拆分）。

### 2.2 user prompts 映射
现有的 planning/execute_step/replan/retry/intent_classify 都是在对话过程中以 user 侧指令发送给模型，本质属于 user prompt 模板，迁移到 `prompts/user/`：
- `tasks/user_prompt*.j2` → `user/query.j2`（结构化用户输入）
- `base/planning.j2 + domains/planning_coding.j2 + tasks/planning_default.j2` → `user/planning.j2`（合并为单文件）
- `tasks/execute_step.j2` → `user/execute_step.j2`
- `tasks/replan.j2` → `user/replan.j2`
- `tasks/plan_patch_retry.j2` → `user/plan_patch_retry.j2`
- `tasks/plan_parse_retry.md` → `user/plan_parse_retry.md`
- `tasks/invalid_step_output_retry.md` → `user/invalid_step_output_retry.md`
- `tasks/intent_classify.j2` → `user/intent_classify.j2`

说明：
- 我们的 PromptManager **默认只支持 `{{ var }}` 替换**，不保证 `{% if %}` 语法；因此 user 模板必须是“纯 `{{ }}`”或由调用方在代码层做条件拼接。

---

## 3. 代码改动点（必须同步）

### 3.1 AgentLoop 默认 stage refs
- `_default_stage_prompts()` 中的默认 ref 全部切到新目录
  - system stage：base=`system/core/global.md`、domain=`system/role/developer.md`、task=`system/context/runtime.j2`
  - planning/execute_step/...：task 指向 `user/*`

### 3.2 Prompt Profile 示例与 Intent 示例
- `.clude/registry/prompt_profiles.example.yaml`：system/user_prompt 的 ref 按新目录更新
- `.clude/registry/intents.example.yaml`：保持 `prompt_profile` 注释示例

### 3.3 旧目录处理策略
为保证一致性与减少歧义：
- 首选：删除旧目录 `prompts/base|domains|tasks`（或保留但不再引用）
- 若需要平滑迁移：保留旧文件但在文档中标记 deprecated（本次倾向“按文档统一”，不再引用旧路径）

---

## 4. 验收与健壮性
- lints 通过
- PromptManager 渲染不输出 `{% %}`
- AgentLoop smoke：能正常构造 system prompt（按新目录）与 user prompt（按新目录）
- prompt_profiles.yaml 不存在时不崩溃（profile 为空配置）


