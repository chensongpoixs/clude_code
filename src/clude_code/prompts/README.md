## prompts 目录说明

> 目的：将工程里“发给大模型的提示词（prompt）”集中管理，避免散落在逻辑代码中导致难维护、难审计、难复用。

### 目录约定

- `base/`：基础层（通用安全边界/通用规范）
- `domains/`：领域层（运行时约束/领域规则，例如 agent_loop/classifier/coding）
- `tasks/`：任务层（具体任务提示词，例如 system_prompt/execute_step/replan/intent_classify）

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


