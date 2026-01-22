# Clude Code 工业级代码工程规范（含企业落地增强版增补）

> **目的**：强制统一工程质量与团队产出风格；并在不破坏原规范的前提下，增补“合并型 Agent（企业落地增强版）”所需的工程约束。  
> **范围**：Python 纯 CLI Code Agent（含 LLM、Tooling、Verification、Observability、Docs、UI）。

---

## 1. 核心准则（必须）

- **单函数长度**：单函数不超过 200 行；超过必须拆分（业务调度与实现细节必须分离）。
- **主流程瘦身**：主函数/主循环（如 `run_turn`）只负责调度，不得堆叠实现细节。
- **中文说明优先**：所有关键逻辑必须有中文说明；涉及英文术语必须紧跟中文解释（双语规则）。
- **禁止 print**：运行期输出一律走 logger（控制台摘要 + 文件日志可回放）。

### 1.1 注释与文档规范（强制）

#### 1.1.1 双语术语规则（强制）
- **英文术语必须紧跟中文解释**：例如 `Control Protocol（控制协议）`、`Hybrid Search（混合检索）`。
- **标题建议双语**：建议 `中文标题（English Title）`。

#### 1.1.2 Python 注释总规则（强制）

> **团队统一风格**：Python **仅允许“声明前注释块（Declaration-leading Comment）”**，并且必须紧贴声明；  
> **禁止**在类体/函数体内使用 Docstring（体内第一条三引号字符串）。

- **类/函数/常量**：说明注释块必须紧贴 `class/def` 或常量定义上一行（不允许插入无关代码/空行）。
- **字段强制**：每个类/函数/常量的声明前注释块必须至少包含：`@author`、`@date`、`@brief`。
- **内容覆盖**：目的（What/Why）、参数/返回（如适用）、注意事项（Notes）、示例（可选）。
- **复杂结构允许 ASCII 图**：状态机、协议、重试流程等。

#### 1.1.3 多语言注释方式（强制）
- **Python**：声明前注释块（三引号），紧贴声明；禁止体内 Docstring。
- **C/C++**：Doxygen `/** ... */` 放在声明前；参数 `@param`、返回 `@return`、备注 `@note`。
- **TS/JS**：JSDoc `/** ... */` 放在声明前；参数 `@param`、返回 `@returns`。
- **YAML**：使用 `#`；示例配置必须包含中文注释；敏感信息建议用环境变量。

#### 1.1.4 声明前注释块模板（Python，强制）

```text
"""
@author 你的名字（Author Name）
@date YYYY-MM-DD
@brief 中文标题（English Title）

功能说明（What & Why）：
- 该类/函数做什么？为什么需要它？

执行流程（Flow）：
- 1) ...
- 2) ...

参数（Params）：
- xxx：中文解释（English Meaning），范围/默认值/示例

返回（Return）：
- 中文解释（Return Meaning）

注意事项（Notes）：
- 约束 1（Constraint 1）
- 约束 2（Constraint 2）
"""
```

---

## 2. 规范使用流程（每次改动必须执行）

- **设计前检查（Before Coding）**：
  - 明确属于哪层：`orchestrator / tooling / llm / verification / observability / docs`
  - 明确契约：是否变更 schema / Pydantic Model / tool protocol
  - 明确安全影响：网络/写文件/执行命令是否受 Policy & Confirm 控制
- **提交前检查（Before Commit）**：
  - 格式化/静态检查通过（见 8.1）
  - 最小验证闭环通过（配置加载、核心 CLI/关键工具 smoke）
  - 日志：控制台不泄露敏感信息；文件日志可复现问题

---

## 3. 架构与模块化（必须）

- **文件容量硬限制**：单个 Python 文件不得超过 2000 行（超过必须拆目录模块）。
- **抗膨胀策略**：
  - 接近 1500 行必须启动重构预警
  - 大类功能必须拆文件（日志/策略/协议/IO/渲染等独立拆分）
- **解耦**：Orchestrator 不得直接包含工具实现细节。
- **注册表模式**：工具等增长组件必须用注册表/插件机制，禁止线性堆叠。
- **协议驱动**：LLM 交互、工具调用必须符合定义好的协议/Schema。
- **显式状态机**：Agent 行为必须受显式状态机驱动，禁止隐式跳转。

### 3.1 模块配置统一管理（Configuration Centralization）

> **核心原则**：所有可配置参数必须集中到 `src/clude_code/config/`，禁止模块自管配置或硬编码。

| 规范项 | 说明 |
|--------|------|
| **配置集中化** | 模块配置定义在 `src/clude_code/config/config.py`；工具配置统一在 `src/clude_code/config/tools_config.py`。 |
| **优先级** | 必须实现：`环境变量 > 配置文件 > 代码默认值`，且只能用 `settings_customise_sources` 实现。 |
| **嵌套 env** | 必须启用 `env_nested_delimiter="__"`。 |
| **敏感信息** | API Key/Token 禁止硬编码；日志必须脱敏（console/file 都不能明文泄露）。 |
| **注入时机** | 配置注入必须在初始化阶段完成（例如 `AgentLoop.__init__`）。 |
| **文档化** | 新增配置项必须同步 `.clude/.clude.example.yaml` 中文注释与示例，并在 docs 说明。 |

### 3.2 配置文件（YAML）格式、位置与生成规则（Commented Template）

| 规范项 | 说明 |
|--------|------|
| **格式统一** | 主配置统一使用 YAML；JSON 仅允许历史兼容读取，不允许作为默认输出。 |
| **主配置位置** | 主配置固定：`~/.clude/.clude.yaml`。 |
| **兼容读取** | 兼容读取：`./.clude/.clude.yaml`、`./clude.yaml`；保存必须写入用户目录主配置。 |
| **中文注释保留** | 生成/保存 YAML 必须保留中文注释：以 `.clude/.clude.example.yaml` 为模板按路径替换值。 |
| **顺序一致** | 顶层 key 顺序必须与 `.clude/.clude.example.yaml` 一致。 |
| **默认值来源** | “生成默认配置”必须来自代码默认值（不受 env/file 污染）。 |
| **示例敏感字段** | 示例文件不得提交真实密钥，必须用空字符串/占位符并注明推荐环境变量。 |

### 3.3 工具配置与日志标准化（Tool Config + Tool Logger）

| 规范项 | 说明 |
|--------|------|
| **工具独立配置** | 每个工具必须有独立配置类（至少 `enabled`、`log_to_file`），统一在 `tools_config.py`。 |
| **统一注入** | 工具配置只能通过 `set_tool_configs(cfg)` 注入、`get_tool_configs()` 读取。 |
| **统一日志** | 工具日志必须走统一 helper（`tooling/logger_helper.py`）。 |
| **错误反馈** | 工具错误必须提供可操作信息；敏感信息禁止出现在日志明文。 |

### 3.4 提示词中心化管理（Prompt Management）

> **核心原则**：所有发送给 LLM 的长提示词必须外置到 `src/clude_code/prompts/`，严禁在逻辑代码中硬编码长字符串。

| 规范项 | 说明 |
|--------|------|
| **目录结构** | 提示词存放于 `src/clude_code/prompts/`，按功能分子目录（如 `agent_loop/`、`classifier/`）。 |
| **加载约定** | 使用 `read_prompt` / `render_prompt` 加载。 |
| **文件格式** | 纯文本 `.md/.txt`；模板 `.j2`。 |
| **禁止硬编码** | 超过 3 行的 LLM 提示词禁止出现在 `.py` 逻辑文件中。 |

#### 3.4.1 提示词管理检查清单（Prompt Checklist）

| 检查项 | 通过标准 |
|--------|----------|
| **新增提示词是否外置** | 新增提示词必须创建 `.md/.j2` 文件放入 `prompts/` 对应目录。 |
| **硬编码检查** | 代码中不得出现超过 3 行的字符串字面量用于 LLM 交互。 |
| **变量传递** | 动态内容必须通过 `render_prompt()` 变量传入，不得在 `.py` 拼接提示词。 |

### 3.5 搜索工具规范（WebSearch / CodeSearch）

#### 3.5.1 搜索资料（WebSearch）：Open-WebSearch MCP 与 Serper（强制）
- 默认优先 `open_websearch_mcp`，失败自动回退 `serper`。
- provider 失败（未配置/超时/网络错误/结构异常）必须自动回退。
- 日志只允许打印 provider/query/数量摘要，禁止泄露 API Key。

#### 3.5.2 代码搜索（CodeSearch）：Grep.app（强制）
- `codesearch` 仅允许网络 code search（Grep.app），不承担本仓库检索职责。

---

## 4. 日志与调试（必须）

- **禁止 print**：一律使用 logger。
- **控制台日志**：简洁可读，只输出摘要。
- **文件日志**：必须包含文件名/行号、异常堆栈（`exc_info=True`），支持滚动。
- **审计/追踪**：关键步骤保留 `trace_id/session_id/project_id` 以便回放定位。

---

## 5. 企业落地增强版增补（不替代原规范）

> 本章是“合并型 Agent（企业落地增强版）”落地所需的**增量约束**，在不破坏原规范前提下生效。

### 5.1 Project ID（多项目隔离，强制）
- `project_id` 默认 `default`；CLI 必须支持 `--project-id`（至少 `chat/doctor/models`）。
- `.clude` 相关路径必须通过 `ProjectPaths` 计算，禁止散落拼接。
- **路径模板**：配置项允许 `{project_id}`，必须被解析（如 `logging.file_path`、`rag.db_path`、`web.cache_dir`）。

### 5.2 Intent Registry（意图注册表，企业 MVP）
- 配置位置：`.clude/registry/intents.yaml`，必须支持 mtime 热加载。
- 路由优先级：精确关键词 > 模糊关键词 > LLM 回退 > 默认。
- 若 `IntentSpec.tools` 非空，运行时必须启用工具白名单拦截（最小权限）。

### 5.3 Plan / PlanPatch 协议增补（强制）
- `Plan` 必须包含：`type="FullPlan"`。
- `PlanPatch` 必须包含：`type="PlanPatch"`。
- PlanPatch 必须检查内部冲突（remove/update/add 互斥），失败需给出明确错误。

### 5.4 工具反馈预算（统一 Output Budget）
- 工具回传给 LLM 的摘要必须受统一预算控制（字符数/命中数/行数）。
- 优先返回结构化摘要而非原始大文本，避免上下文爆炸。

---

## 6. 质量门禁（必须）

### 6.1 可执行入口（推荐默认）
- 依赖安装：`pip install -e ".[dev]"`
- 格式化：`ruff format .`
- Lint：`ruff check .`
- 类型检查：`mypy src`

### 6.2 测试与验证（必须）
- **单元测试**：关键解析/规范化/策略判断必须可测。
- **集成验证**：至少具备一套 smoke：配置加载、核心 CLI、关键工具闭环。
- **契约变更必更新 docs**：prompt/schema/tool feedback 变更必须同步文档与示例。

---

## 7. 安全与稳健性（必须）

- **写/执行必须确认（HITL）**：写文件、执行命令必须确认或显式 `--yes`。
- **默认最小权限**：网络/写/exec 默认要走 policy+confirm。
- **失败可回放**：异常必须进文件日志；控制台只显示友好摘要。

---

## 8. UI 与可视化（必须）

- 三种 UI（classic/enhanced/opencode）核心事件语义必须一致。
- 新增事件必须同步 UI 渲染。

---

## 9. 文档质量门禁（必须）

- 英文术语必须带中文解释。
- 文档必须可读、可执行、可验收（包含检查清单/示例/路径）。


