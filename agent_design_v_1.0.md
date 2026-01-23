# 合并型 Agent 工程设计文档（企业级落地增强版 · Prompt Profile 架构融合）

> **文档定位**：公司级 Agent / Prompt Engineering / Orchestrator 统一设计规范
> **适用对象**：自动执行型 Agent、规划 + 执行分离型 Agent、生产级 AI 系统
> **目标读者**：平台架构师、AI 工程负责人、安全与合规负责人

---

## 0. 设计目标与核心原则

### 0.1 设计目标

解决企业级 Agent 系统中以下核心问题：

* 不同用户意图共用同一 Prompt，行为不可控
* System Prompt / User Prompt 职责混乱
* 高风险任务无法审计与人工介入
* 多项目并行下 Prompt 难以治理

### 0.2 设计原则（强制）

1. **意图决定行为类型，而非 Prompt 内容**
2. **Prompt 必须资产化、版本化、可回滚**
3. **风险前置，执行后置**
4. **模型不参与策略决策**
5. **多项目强隔离，最小权限运行**

---

## 1. 总体架构：意图驱动的合并型 Agent

### 1.1 架构总览

系统采用「合并型 Agent + 条件分流」架构：

```text
用户输入（Project_ID）
   │
   ▼
意图识别（多轮上下文 + 项目限定）
   │
   ▼
Intent Registry
   │
   ▼
Prompt Profile Selector
   │
   ├─ Unified Mode  ──> Prompt 组装 ──> 执行 ──> 审计
   │
   └─ Split Mode
        ├─ Planner（Plan + Risk）
        ├─ Review / Approval
        └─ Executor（受控执行）
```

---

## 2. Prompt Profile 设计（公司级核心抽象）

### 2.1 Prompt Profile 定义

> **Prompt Profile 是 Intent 与 Prompt 资产之间的唯一中间抽象层。**

形式化定义：

```text
Prompt Profile = System Prompt 组合 + User Prompt 模板
```

### 2.2 Prompt Profile 职责边界

| 能做            | 不能做      |
| ------------- | -------- |
| 决定 Agent 行为边界 | 承载具体业务逻辑 |
| 控制风险与权限       | 动态生成规则   |
| 组合 Prompt 资产  | 由模型选择    |

---

## 3. Prompt 工程体系（分层 + 继承）

### 3.1 System Prompt 四层模型（强制）

| 层级      | 职责           | 是否必选 |
| ------- | ------------ | ---- |
| Core    | 全局规范 / 价值观   | 必选   |
| Role    | Agent 角色能力   | 必选   |
| Policy  | 风险 / 合规 / 权限 | 按需   |
| Context | 阶段 / 环境增强    | 可选   |

**System Prompt 只能收紧权限，禁止放权。**

---

### 3.2 User Prompt 模板规范

User Prompt 模板用于：

* 结构化用户输入
* 明确输出格式与边界
* 收敛自然语言差异

**禁止直接使用原始用户输入作为最终 User Prompt。**

---

### 3.3 Prompt 目录结构（统一规范）

```text
src/clude_code/prompts/
├── system/
│   ├── core/
│   │   └── global.md                  # 全局规范/安全边界（必选）
│   ├── role/
│   │   ├── developer.md               # 角色：开发
│   │   ├── analyst.md                 # 角色：分析
│   │   ├── operator.md                # 角色：运维
│   │   ├── architect.md               # 角色：架构
│   │   ├── security.md                # 角色：安全
│   │   ├── developer_readonly.md      # 组合角色（示例：role+policy 合并）
│   │   ├── operator_high_risk.md      # 组合角色（高风险）
│   │   └── security_high_risk.md      # 组合角色（高风险）
│   ├── policy/
│   │   ├── readonly.md                # 只读/最小权限（示例）
│   │   └── high_risk.md               # 高风险治理（示例）
│   └── context/
│       └── runtime.j2                 # 运行期注入：工具清单/项目记忆/环境信息（建议必选）
└── user/
    ├── stage/                         # “阶段协议”提示词（规划/执行/重规划/重试/分类）
    │   ├── planning.j2
    │   ├── execute_step.j2
    │   ├── replan.j2
    │   ├── plan_patch_retry.j2
    │   ├── plan_parse_retry.md
    │   ├── invalid_step_output_retry.md
    │   └── intent_classify.j2
    └── intent/                        # “意图模板”提示词（结构化用户输入）
        ├── dev/
        │   ├── coding_task.j2
        │   └── error_diagnosis.j2
        ├── analysis/
        │   ├── repo_analysis.j2
        │   ├── documentation_task.j2
        │   └── technical_consulting.j2
        ├── design/
        │   └── project_design.j2
        ├── security/
        │   └── security_consulting.j2
        ├── meta/
        │   ├── query.j2
        │   └── capability_query.j2
        └── chat/
            ├── general_chat.j2
            └── casual_chat.j2
```

> 注：当前运行时的“合法 prompt 根路径”以 `src/clude_code/prompts/{system,user}` 为准。

#### 3.3.1 文件类型与版本化约定（SemVer）

- `*.md`：纯文本提示词（通常不需要变量）
- `*.j2`：模板提示词（可包含 `{{ var }}`，必要时支持 Jinja2 语法）
- 默认版本：`xxx.md` / `xxx.j2`
- 指定版本：`xxx_v1.2.3.md` / `xxx_v1.2.3.j2`
- 允许 YAML front matter（元数据契约），例如：

```text
---
title: "System Core: Global Rules (current)"
version: "1.0.0"
layer: "system|user"
---
正文（可包含 {{ var }}）
```

#### 3.3.2 模板变量约定（运行时注入）

- `system/context/runtime.j2`：
  - `tools_section`：可用工具清单（简版）
  - `project_memory`：项目记忆（来自 `CLUDE.md`/`CLAUDE.md`，可能为空）
  - `env_info`：环境信息（包含 repo_map；可能被截断）
- `user/intent/*/*.j2`（结构化用户输入模板）常用变量：
  - `user_text`、`planning_prompt`、`project_id`、`intent_name`、`risk_level`

---

## 4. Prompt Profile Registry（配置中心）

```yaml
prompt_profiles:
  readonly_query:
    description: 只读查询
    system_prompts:
      - system/core/global.md
      - system/role/developer_readonly.md
      - system/context/runtime.j2
    user_prompt_template: user/intent/meta/query.j2
    risk_level: LOW

  prod_operation_guarded:
    description: 高风险生产操作
    system_prompts:
      - system/core/global.md
      - system/role/operator_high_risk.md
      - system/context/runtime.j2
    user_prompt_template: user/intent/dev/coding_task.j2
    risk_level: CRITICAL
```

---

## 5. Intent Registry（意图注册表）

```yaml
intents:
  - intent: query_balance
    project_id: fintech_app
    prompt_profile: readonly_query

  - intent: deploy_prod
    project_id: infra_platform
    prompt_profile: prod_operation_guarded
```

#### 5.1 规则（推荐路径）

- **推荐**：Intent → `prompt_profile`（由 Profile 组合 `system_prompts` + `user_prompt_template`）。
- **允许（高级用法）**：对特定 stage 进行覆盖（例如只覆盖 `execute_step`），但必须遵守：
  - 优先级：Intent overrides > Project defaults > 内置默认
  - 可观测：变更必须可审计、可回滚（结合版本化文件命名与运维工具）

---

## 6. Orchestrator 核心逻辑（增强版）

### 6.1 执行流程

1. 意图识别
2. 选择 Prompt Profile
3. 装配 System Prompt
4. 渲染 User Prompt
5. 执行 / 规划 / 审批

### 6.2 伪代码示例

```python
profile = profile_registry.get(intent.prompt_profile)

messages = []
for sp in profile.system_prompts:
    messages.append({"role": "system", "content": load(sp)})

user_prompt = render(profile.user_prompt_template, user_input)
messages.append({"role": "user", "content": user_prompt})
```

> 说明：在当前工程实现中，`render()` 的输入通常是一个变量字典（而不是仅传 `user_input` 字符串），以保证模板稳定可运营：
>
> - `user_text`
> - `planning_prompt`
> - `project_id`
> - `intent_name`
> - `risk_level`

---

## 7. 风险控制与 Human-in-the-Loop

| 风险等级     | 执行策略        |
| -------- | ----------- |
| LOW      | 自动执行        |
| MEDIUM   | 自动执行 + 回滚   |
| HIGH     | Plan Review |
| CRITICAL | 人工审批 + 沙箱   |

风险等级来源：**Prompt Profile + Intent 联合约束**。

---

## 8. 多项目隔离与审计

* Project 级 Token / 数据隔离
* Prompt / Profile 变更审计
* 全链路 Trace ID

---

## 9. 企业级落地建议

* Prompt Profile 作为平台级配置
* 新项目强制接入
* 老项目按风险迁移

---

## 10. 总结

本设计实现：

* 根据用户意图动态选择 System Prompt 与 User Prompt
* Prompt 行为工程化、可治理
* Agent 行为可控、可审计、可扩展

 
