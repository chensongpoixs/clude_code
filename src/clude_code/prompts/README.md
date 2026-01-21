## prompts 目录说明

> 目的：将工程里“发给大模型的提示词（prompt）”集中管理，避免散落在逻辑代码中导致难维护、难审计、难复用。

### 目录约定

- `agent_loop/`：主 AgentLoop 的 system/planning/execute/replan 等提示词
- `classifier/`：意图分类器等“决策门”提示词

### 文件约定

- `*.md`：纯文本提示词（无变量）
- `*.j2`：Jinja2 模板提示词（有变量占位符）


