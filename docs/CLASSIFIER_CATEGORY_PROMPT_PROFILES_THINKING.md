# 扩展意图分类（classifier.py 31-55）对应 Prompt Profile 完善方案（思路 + 落地清单）

> 对齐：`src/clude_code/orchestrator/classifier.py` IntentCategory（31-55）

---

## 1. 目标

用户把意图类别从 5 类扩展为更细粒度的多类后，需要做到：
- 每个类别都能映射到一个默认 Prompt Profile（即使 registry 没命中、intent 没配置 prompt_profile）
- 每个 Profile 具备**不同的 system/user prompts**（至少 user 模板不同；必要时 role/policy 不同）
- 目录结构必须对齐最新规范：`prompts/system/*` 与 `prompts/user/*`

---

## 2. 现状（需要补齐的点）

当前代码已具备：
- Prompt Profile Registry（`.clude/registry/prompt_profiles.yaml`，示例为 `.example.yaml`）
- AgentLoop 在 intent 未指定 prompt_profile 时，可按分类结果选择 `classifier_*` 默认 profile（已有 5 类版本）
- system/user prompts 已迁移到 `system/*` 与 `user/*`

待补齐：
- 分类 prompt `user/intent_classify.j2` 的类别列表仍是旧 5 类，需更新为新类别集合
- `prompt_profiles.example.yaml` 需要新增新类别 profile
- 新类别对应的 user 模板 prompt 文件需要补齐（例如 error_diagnosis、documentation_task 等）
- AgentLoop 的 `cat_to_profile` 映射与 “是否启用 planning” 规则需扩展（比如 CASUAL_CHAT 应跳过 planning）

---

## 3. 类别 → 默认 Profile → system/user 组合（MVP 设计）

### 3.1 约定
- profile 命名：`classifier_<category_lower>`（例：classifier_error_diagnosis）
- system 组合（MVP）：
  - core：`system/core/global.md`（固定）
  - role：按类别选择（developer/analyst/operator/architect/security）
  - context：`system/context/runtime.j2`（固定）
- user 模板：按类别选择对应 `user/*.j2`

### 3.2 映射表（MVP）
- CODING_TASK → profile=`classifier_coding_task`
  - role=developer，user=`user/coding_task.j2`
- ERROR_DIAGNOSIS → profile=`classifier_error_diagnosis`
  - role=developer，user=`user/error_diagnosis.j2`
- REPO_ANALYSIS → profile=`classifier_repo_analysis`
  - role=analyst，user=`user/repo_analysis.j2`
- DOCUMENTATION_TASK → profile=`classifier_documentation_task`
  - role=analyst，user=`user/documentation_task.j2`
- TECHNICAL_CONSULTING → profile=`classifier_technical_consulting`
  - role=analyst，user=`user/technical_consulting.j2`
- PROJECT_DESIGN → profile=`classifier_project_design`
  - role=architect，user=`user/project_design.j2`
- SECURITY_CONSULTING → profile=`classifier_security_consulting`
  - role=security + policy=high_risk（更保守），user=`user/security_consulting.j2`
- CAPABILITY_QUERY → profile=`classifier_capability_query`
  - role=analyst，user=`user/capability_query.j2`
- GENERAL_CHAT → profile=`classifier_general_chat`
  - role=analyst，user=`user/general_chat.j2`
- CASUAL_CHAT → profile=`classifier_casual_chat`
  - role=analyst，user=`user/casual_chat.j2`
- UNCERTAIN → profile=`classifier_uncertain`
  - role=analyst，user=`user/query.j2`（兜底）

---

## 4. 代码落地点

### 4.1 分类 prompt 更新
文件：`src/clude_code/prompts/user/intent_classify.j2`
- 类别列表必须与 `IntentCategory` 保持一致（否则 LLM 会输出“旧类别名”导致解析/分流混乱）

### 4.2 AgentLoop 映射扩展
文件：`agent_loop.py::_resolve_stage_prompt_triplet`
- 更新 `cat_to_profile`，覆盖新类别

### 4.3 planning 决策门扩展
文件：`agent_loop.py::_classify_intent_and_decide_planning`
- 对 CAPABILITY_QUERY / GENERAL_CHAT / CASUAL_CHAT：默认禁用 planning（避免闲聊进入规划）

### 4.4 Prompt 资产补齐
- `system/role/architect.md`（架构设计）
- `system/role/security.md`（安全咨询）
- `user/*.j2`：新增类别对应模板
- `.clude/registry/prompt_profiles.example.yaml`：新增 profiles

---

## 5. 验收（最小）
- 每个新类别都能选到 profile（不崩溃）
- user_content 会变（能明显看出类别差异）
- `clude prompts validate` 通过


