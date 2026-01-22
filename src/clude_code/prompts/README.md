## prompts 目录说明

> 目的：将工程里“发给大模型的提示词（prompt）”集中管理，避免散落在逻辑代码中导致难维护、难审计、难复用。

### 目录约定

- `system/`：系统提示词资产（对齐 `agent_design_v_1.0.md`）
  - `system/core/`：全局规范/价值观/安全边界（Core）
  - `system/role/`：角色能力与运行期约束（Role）
  - `system/policy/`：风险/合规/权限约束（Policy）
  - `system/context/`：运行期上下文注入（工具清单/项目记忆/环境信息）（Context）
- `user/`：用户提示词模板（按用途分子目录）
  - `user/intent/`：按意图的“结构化用户输入模板”（例如 coding_task / repo_analysis / capability_query）
  - `user/stage/`：按阶段的 user prompt（planning / execute_step / replan / 各类 retry / intent_classify）

### 更像业界的目录分组（推荐）

`user/intent/` 建议进一步按“业务域/场景”分组（避免意图数量增大后扁平目录失控）：

- `user/intent/dev/`：开发执行类（coding_task / error_diagnosis）
- `user/intent/analysis/`：分析解释类（repo_analysis / documentation_task / technical_consulting）
- `user/intent/design/`：架构设计类（project_design）
- `user/intent/security/`：安全类（security_consulting）
- `user/intent/meta/`：元交互/兜底（capability_query / query）
- `user/intent/chat/`：对话类（general_chat / casual_chat）

### 模板注入变量清单

为保证模板编写的一致性，`AgentLoop` 在渲染 `user_prompt` stage 时固定提供以下变量：

- `user_text`：原始用户输入文本。
- `planning_prompt`：若开启规划，则包含 JSON 规划协议提示词；否则为空字符串。
- `project_id`：当前项目 ID。
- `intent_name`：识别出的意图名称。
- `risk_level`：该意图的风险等级。

### 遗留目录（Deprecated）

仓库中可能还存在空目录：`base/`、`domains/`、`tasks/`。

- 这些目录是旧 Prompt 体系遗留，**当前运行时与校验（`clude prompts validate`）只认可 `system/` 与 `user/`**。
- 请勿在这些目录下新增 prompt 文件；如发现有文件，应迁移到 `system/` 或 `user/` 后再删除旧文件。

### 文件约定

- `*.md`：纯文本提示词（无变量）
- `*.j2`：Jinja2 模板提示词（有变量占位符）

### 版本化约定（SemVer）

- 默认版本：`xxx.md` / `xxx.j2`
- 指定版本：`xxx_v1.2.3.md` / `xxx_v1.2.3.j2`
- Prompt 文件可包含 YAML front matter（元数据契约）：

```text
---
title: "..."
version: "1.0.0"
layer: "base|domain|task"
tools_expected: [grep, read_file]
constraints:
  - "..."
---
正文（可包含 {{ var }}）
```


