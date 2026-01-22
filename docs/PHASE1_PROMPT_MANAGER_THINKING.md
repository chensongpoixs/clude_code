# Phase 1：Prompt 三层继承与版本体系——思考过程与设计说明

> 目标：实现 Prompt 三层继承体系（Base / Domain / Task）与版本工程能力（SemVer + 回滚指针），并与 Intent Registry 对齐；本阶段按你的最新要求：**不再兼容旧提示词工程**（删除旧 `agent_loop/`、`classifier/` 目录，统一迁移到三层结构）。

---

## 1. 需求拆解（What/Why）

### 1.1 现状问题
- Prompt 分散或难以做“企业级运营”（版本、回滚、灰度、审计）。
- 不同项目/不同任务需要“不同约束与工具白名单”，但缺少标准化入口。
- 需要与 `Intent Registry` 对齐：`intent -> prompt_ref/version/tools/risk_level`。

### 1.2 Phase 1 的最小闭环（对齐 3.3 规则）
- **PromptManager**：支持 base/domain/task 三层组合与版本选择（SemVer），解析 YAML front matter 元数据。
- **版本化**：支持 `task_x_v1.3.j2` 命名；当指定版本不存在时可回退默认文件（不带版本后缀）。
- **回滚**：通过 `current -> previous` 指针实现快速回滚（`prompt_versions.json`）。
- **集成点**：
  - 与 `Intent Registry` 对接：registry 决定加载哪个 prompt 版本。
  - 非兼容模式：旧提示词工程不再保留；所有提示词都应迁移到 `base/ domains/ tasks/`。

---

## 2. Prompt 三层目录与命名约定（Structure）

在 `src/clude_code/prompts/` 下使用三类目录（不再保留 `agent_loop/`、`classifier/`）：

```
src/clude_code/prompts/
├── base/        # Base layer：通用规范/底座约束（跨任务、跨领域可复用）
├── domains/     # Domain layer：领域/运行时约束（例如 agent_loop / classifier / coding）
└── tasks/       # Task layer：具体任务提示词（system_prompt/execute_step/replan/intent_classify 等）
```

### 2.1 文件命名（SemVer）
- **默认版本**：`xxx.md` / `xxx.j2`
- **指定版本**：`xxx_v1.2.3.md` / `xxx_v1.2.3.j2`
- `PromptManager` 的查找顺序：
  1) 有 version：优先找 `_v{version}` 文件
  2) 找不到则回退默认文件（不带版本后缀）

> 设计取舍：Phase 1 先支持 **精确版本**，避免引入复杂的范围解析（`^1.2` / `~1.2`）。后续可扩展。

---

## 3. YAML Front Matter 元数据契约（Metadata Contract）

Prompt 文件允许在开头携带 YAML front matter：

```text
---
name: base_coding
version: 1.0.0
layer: base            # base/domain/task
tools_expected: [grep, read_file]
constraints:
  - "禁止输出代码块外的解释"
---
正文内容（可包含 {{ var }} 变量）
```

### 3.1 元数据用途
- **审计**：记录 prompt 的 name/version/layer。
- **约束**：以结构化方式声明 constraints/tools_expected（未来可做自动校验）。
- **组合**：PromptManager 在三层组合时做 merge（去重合并 list）。

### 3.2 兼容性原则
- 没有 front matter 也能工作：元数据为空，body 为全文。
- `render_prompt()` 仍按文件读文本替换变量；新增 PromptManager 会负责“解析 front matter + 组合 + 再渲染”。

---

## 4. 三层组合策略（Inheritance）

Phase 1 采用“显式组合（Explicit Composition）”，而不是在 Prompt 内写 `extends:` 自动继承，原因：
- 可审计、可控：组合关系由 Orchestrator 明确决定
- 不破坏现有 prompt 文件结构
- 易于与 Intent Registry 对齐

组合规则：
- `base_text + "\n\n" + domain_text + "\n\n" + task_text`
- 最终对拼接后的文本做一次变量渲染（`{{ var }}` 替换）

---

## 5. 与 Intent Registry 的对齐（Integration）

### 5.1 输入来源
- `ProjectConfig.base_prompt_ref`：Base 层（可选）
- `ProjectConfig.domain_prompt_ref`：Domain 层（可选，Phase 1 新增字段）
- `IntentSpec.prompt_ref`：Task 层（可选）
- `IntentSpec.prompt_version`：Task 层版本（可选）

### 5.2 输出到 AgentLoop 的形态
- `extra_instructions: str`：注入到 planning/execute prompt 内部的“额外约束块”
- 若任何一层不存在，则忽略该层（保持向后兼容）

---

## 6. 回滚策略（Rollback Strategy）

Phase 1 的“回滚”先做 **能力准备**（实现接口与存储格式），不强制在 CLI 暴露：
- 存储位置建议：`.clude/registry/prompt_versions.json`
- 结构：
```json
{
  "prompts": {
    "tasks/code_review_prompt.j2": { "current": "1.0.1", "previous": "1.0.0" }
  }
}
```

运行时选择顺序：
1) IntentSpec.prompt_version（显式指定，最高优先）
2) prompt_versions.json 中的 current
3) 默认文件

> 这样可以做到：线上事故时只需要把 current 回滚到 previous，无需改代码。

---

## 7. 需要实现的代码点（Implementation Checklist）

- [ ] 新增 `src/clude_code/prompts/prompt_manager.py`
  - parse front matter
  - resolve versioned file
  - compose base/domain/task
  - 变量渲染（复用现有 `{{ var }}` 规则）
- [ ] 扩展 `ProjectConfig`：新增 `domain_prompt_ref: Optional[str]`
- [ ] AgentLoop 接入：
  - intent 路由后生成 `self._current_extra_instructions`
  - `_build_planning_prompt()` / `execute_step_prompt` 传入 `extra_instructions`
- [ ] Prompt 模板增补变量：
  - `agent_loop/planning_prompt.j2` 增加 `{{ extra_instructions }}`
  - `agent_loop/execute_step_prompt.j2` 增加 `{{ extra_instructions }}`

---

## 8. 验收点（Acceptance Criteria）

- 不配置 registry/prompts 时，行为与现有版本一致（兼容性）。
- 配置 IntentSpec.prompt_ref 后，planning/execute 的 prompt 能包含额外约束块。
- 指定 `prompt_version` 时优先加载 `_v{version}` 文件，找不到则回退默认文件。
- 解析失败（front matter/文件不存在）不崩溃：控制台警告 + file-only 详细堆栈，最终回退到“无额外约束”。


