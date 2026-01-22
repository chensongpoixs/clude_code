# Prompt Profile 改造健壮性分析报告

> 目标：检查“按意图分类驱动 Prompt Profile”的实现是否存在逻辑漏洞、路径断裂或变量失配。

---

## 1. 目录结构完整性分析

### 1.1 现状（合理）
- 结构已对齐工业界做法：`system/{core,role,policy,context}` + `user/{intent,stage}`。
- `user/intent/` 已按业务域（dev/analysis/design/security/meta/chat）细分。

### 1.2 潜在风险点
- **遗留目录**：`prompts/base|domains|tasks` 虽为空但仍物理存在，容易误导新开发者。
- **校验死角**：`clude prompts validate` 目前对“子目录嵌套”的覆盖是否严谨（经查，目前的 `rglob` 逻辑能覆盖到子目录，已确认 OK）。

---

## 2. 逻辑路由与映射分析

### 2.1 意图映射覆盖率
- **`AgentLoop` 分类映射**：`cat_to_profile` 覆盖了 `IntentCategory` 的全部 **11 个枚举值**。
  - 覆盖情况：CODING_TASK, ERROR_DIAGNOSIS, REPO_ANALYSIS, DOCUMENTATION_TASK, TECHNICAL_CONSULTING, PROJECT_DESIGN, SECURITY_CONSULTING, CAPABILITY_QUERY, GENERAL_CHAT, CASUAL_CHAT, UNCERTAIN。
- **YAML 示例同步**：`.clude/registry/prompt_profiles.example.yaml` 已补齐上述 11 个 profile 定义。

### 2.2 决策门一致性
- `CASUAL_CHAT` 逻辑：已正确加入“跳过 planning”名单（与 GENERAL_CHAT 一致），符合预期。

---

## 3. 变量对齐分析（关键问题）

### 3.1 `AgentLoop` 变量注入点
注入变量：`planning_prompt`, `user_block`, `project_id`, `intent_name`, `risk_level`, `user_text`。

### 3.2 模板使用情况抽查
- **问题发现**：`user/intent/meta/query.j2` 仍在使用 `{{ user_block }}`。
- **分析**：
  - `user_block` 是代码中固化的 `f"## 用户输入\n{user_text}"`。
  - 其他所有业务模板（如 `coding_task.j2`）都已改用原生的 `{{ user_text }}` 并由模板自定标题。
  - **不合理点**：`user_block` 导致“标题内容”在 Python 代码和模板中割裂，不符合“提示词资产化”原则。

---

## 4. 完善建议（Action Plan）

1. **统一变量**：废弃 Python 代码中的 `user_block` 构造逻辑，统一让模板使用 `user_text`。
2. **修正 `query.j2`**：将 `{{ user_block }}` 改为结构化的 `{{ user_text }}` 展现形式。
3. **清理物理空目录**：删除物理存在的空目录 `prompts/base|domains|tasks` 以保持工作区整洁。
4. **同步 README**：在 `prompts/README.md` 中明确说明注入变量清单，防止后续编写模板时“盲写”变量名。

