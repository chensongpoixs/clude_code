# Clude Code 工业级代码工程规范

> **目的**：这份规范用于强制统一工程质量与团队产出风格。任何实现/改动都必须能在本规范下被解释、被验收、被回归。  
> **范围**：Python 纯 CLI Code Agent（含 LLM、Tooling、Verification、Observability、Docs）。

## 1. 核心准则（必须）

- **单函数长度**：单函数不超过 200 行；超过必须拆分（业务调度与实现细节必须分离）。
- **主流程瘦身**：主函数/主循环（如 `run_turn`）只负责调度，不得堆叠实现细节。
- **中文说明优先**：所有关键逻辑必须有中文说明；涉及英文术语必须紧跟中文解释（双语规则）。
- **禁止 print**：运行期输出一律走 logger（控制台摘要 + 文件日志可回放）。

### 1.1 注释与文档规范（强制）

#### 1.1.1 双语术语规则（强制）
- **英文术语必须紧跟中文解释**：例如 `Control Protocol（控制协议）`、`Hybrid Search（混合检索）`。
- **标题必须双语**：建议 `中文标题（English Title）`。

#### 1.1.2 Python 注释总规则（强制）

> **团队统一风格**：Python **仅允许“声明前注释块（Declaration-leading Comment）”**，并且必须紧贴声明；  
> **禁止**在类体/函数体内使用 Docstring（体内第一条三引号字符串）。

- **类/函数/常量**：说明注释块必须紧贴 `class/def` 或常量定义上一行（不允许插入无关代码/空行）。
- **字段强制**：每个类/函数/常量的声明前注释块必须至少包含：
  - `@author`（作者/责任人，Author）
  - `@date`（日期，Date）
  - `@brief`（一句话双语摘要，Brief）
- **内容覆盖**：除上述字段外，注释内容还必须覆盖：目的（What/Why）、参数/返回（如适用）、注意事项（note）、示例（可选）。
- **复杂结构允许 ASCII 图**：状态机、协议、二进制结构、重试流程等。

#### 1.1.3 多语言注释方式（强制）
- **Python**：声明前注释块（三引号），紧贴声明；禁止体内 Docstring。
- **C/C++**：Doxygen `/** ... */` 放在声明前；参数 `@param`、返回 `@return`、备注 `@note`。
- **TS/JS**：JSDoc `/** ... */` 放在声明前；参数 `@param`、返回 `@returns`。
- **YAML**：使用 `#`；示例配置必须包含中文注释，说明关键字段与推荐配置方式（敏感信息建议用环境变量）。

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

示例（Example）：
...（可选）
"""
```

## 2. 规范使用流程（每次改动必须执行）

- **设计前检查（Before Coding）**：
  - 明确属于哪层：`orchestrator / tooling / llm / verification / observability / docs`
  - 明确契约：是否变更 schema / Pydantic Model / tool protocol
  - 明确安全影响：网络/写文件/执行命令是否受 Policy & Confirm 控制
- **提交前检查（Before Commit）**：
  - 格式化/静态检查通过（见 5.1）
  - 最小验证闭环通过（配置加载、核心 CLI/关键工具 smoke）
  - 日志：控制台不泄露敏感信息；文件日志可复现问题

## 3. 架构与模块化（必须）

- **文件容量硬限制**：单个 Python 文件不得超过 2000 行（超过必须拆目录模块）。
- **抗膨胀策略**：
  - 接近 1500 行必须启动重构预警
  - 大类功能必须拆文件（日志/策略/协议/IO/渲染等独立拆分）
- **解耦**：Orchestrator 不得直接包含工具实现细节。
- **注册表模式**：不断增长的组件（如工具）必须使用注册表/插件机制，禁止线性堆叠。
- **协议驱动**：LLM 交互、工具调用必须符合定义好的协议/Schema。
- **显式状态机**：Agent 行为必须受显式状态机驱动，禁止隐式跳转。

### 3.1 模块配置统一管理（Configuration Centralization）

> **核心原则**：所有可配置参数必须集中到 `src/clude_code/config/`，禁止模块自管配置或硬编码。

| 规范项 | 说明 |
|--------|------|
| **配置集中化** | 模块配置定义在 `src/clude_code/config/config.py`；工具配置统一在 `src/clude_code/config/tools_config.py`。 |
| **优先级** | 必须实现：`环境变量 > 配置文件 > 代码默认值`，且只能用 `settings_customise_sources` 实现，禁止 `__init__` 手工合并导致优先级反转。 |
| **嵌套 env** | 必须启用 `env_nested_delimiter="__"`，确保 `CLUDE_LLM__MAX_TOKENS` 等嵌套项可生效。 |
| **敏感信息** | API Key/Token 禁止硬编码；日志必须脱敏（console/file 都不能明文泄露）。 |
| **注入时机** | 配置注入必须在初始化阶段完成（例如 `AgentLoop.__init__`），禁止运行时到处读 env/file。 |
| **文档化** | 新增配置项必须同步 `.clude/.clude.example.yaml` 中文注释与示例，并在 docs 说明。 |

### 3.2 配置文件（YAML）格式、位置与生成规则（Commented Template）

| 规范项 | 说明 |
|--------|------|
| **格式统一** | 主配置统一使用 YAML；JSON 仅允许历史兼容读取，不允许作为默认输出。 |
| **主配置位置** | 主配置固定：`~/.clude/.clude.yaml`。 |
| **兼容读取** | 允许兼容读取：`./.clude/.clude.yaml`、`./clude.yaml`，但保存/生成必须写入用户目录主配置。 |
| **中文注释保留** | 生成/保存 YAML 必须保留中文注释：以 `.clude/.clude.example.yaml` 为模板按路径替换值（禁止直接 dump 丢注释）。 |
| **顺序一致** | 顶层 key 顺序必须与 `.clude/.clude.example.yaml` 一致，便于 diff 与排查。 |
| **默认值来源** | “生成默认配置”必须来自代码默认值（不受 env/file 污染），推荐 `model_construct()`。 |
| **示例敏感字段** | `.clude/.clude.example.yaml` 不得提交真实密钥，必须用空字符串/占位符并注明推荐环境变量。 |

### 3.3 工具配置与日志标准化（Tool Config + Tool Logger）

| 规范项 | 说明 |
|--------|------|
| **工具独立配置** | 每个工具必须有独立配置类（至少 `enabled`、`log_to_file`），统一在 `tools_config.py`。 |
| **新增工具默认配置必备** | 新增工具必须在全局 `ToolConfigs` 增加默认字段，保证“工具可用即有默认配置”。 |
| **统一注入** | 工具配置只能通过 `set_tool_configs(cfg)` 注入、`get_tool_configs()` 读取；禁止工具模块直接读 env/file。 |
| **统一日志** | 工具日志必须走统一 helper（如 `tooling/logger_helper.py`），并遵循全局日志配置与工具 `log_to_file`。 |
| **错误反馈** | 工具错误必须提供可操作信息；敏感信息禁止出现在日志明文。 |

### 3.4 提示词中心化管理（Prompt Management）

> **核心原则**：所有发送给 LLM 的长篇提示词（System Prompt、Planning Prompt、Step Prompt 等）必须外置到 `src/clude_code/prompts/` 目录，严禁在逻辑代码中硬编码长字符串。

| 规范项 | 说明 |
|--------|------|
| **目录结构** | 提示词存放于 `src/clude_code/prompts/`，按功能分子目录（如 `agent_loop/`、`classifier/`）。 |
| **加载约定** | 使用 `from clude_code.prompts import read_prompt, render_prompt` 加载。 |
| **文件格式** | 纯文本使用 `.md` 或 `.txt`；带变量模板使用 `.j2`（即便不依赖 jinja2 也要保持扩展名一致性）。 |
| **禁止硬编码** | 超过 3 行的 LLM 提示词禁止出现在 `.py` 逻辑文件中。 |
| **解耦** | 逻辑代码只负责准备变量（Vars），不负责提示词的遣词造句。 |

#### 3.3.1 搜索资料（WebSearch）工具：Open-WebSearch MCP 与 Serper（强制）

> **目标**：支持两个“搜索资料来源”（Search Provider），可通过配置选择；默认优先使用 **Open-WebSearch MCP**，失败自动回退 **Serper**。

- **可配置选择（Configurable Choice）**：
  - `open_websearch_mcp`：优先（Preferred），用于接入本地/自建的 Open-WebSearch MCP 服务器
  - `serper`：备用（Fallback），用于调用 Serper（Google 搜索 API）
- **优先级与回退（Priority & Fallback）**：
  - 由 `search.websearch_providers` 指定优先级列表（例如 `["open_websearch_mcp", "serper"]`）
  - 默认必须是：`open_websearch_mcp > serper`
  - 任何 provider 发生：未配置/超时/网络错误/返回结构异常，都必须自动回退到下一个 provider
- **敏感信息（Sensitive Info）**：
  - API Key 必须使用环境变量或私有配置文件注入，示例文件不得提交真实密钥
  - 推荐环境变量（嵌套 env）：`CLUDE_SEARCH__SERPER_API_KEY`、`CLUDE_SEARCH__OPEN_WEBSEARCH_MCP_API_KEY`
- **日志（Logging）**：
  - 只允许打印 provider、query、结果数量等摘要
  - 禁止输出 API Key 明文；失败堆栈写入 file-only 日志，控制台输出可读摘要

## 4. 日志与调试（必须）

- **禁止 print**：一律使用 logger。
- **控制台日志**：简洁、可读、适度颜色；只输出关键信息摘要。
- **文件日志**：必须包含文件名/行号、异常堆栈（`exc_info=True`）、原始上下文，支持滚动。
- **审计/追踪**：关键步骤保留 trace_id / session_id 以便回放定位。

## 5. 质量门禁（必须）

### 5.1 可执行入口（推荐默认）
- 依赖安装：`pip install -e ".[dev]"`
- 格式化：`ruff format .`
- Lint：`ruff check .`
- 类型检查：`mypy src`

### 5.2 测试与验证（必须）
- **单元测试**：关键解析/规范化/策略判断必须可测。
- **集成验证**：至少具备一套 smoke 验证：配置加载、核心 CLI 启动、关键工具调用闭环。
- **契约变更必更新 docs**：prompt/schema/tool feedback 变更必须同步文档与示例。

## 6. 安全与稳健性（必须）

- **写/执行必须确认（HITL）**：写文件、执行命令必须经过确认或显式 `--yes`。
- **默认最小权限**：`allow_network=False` 默认关闭网络。
- **失败可回放**：异常必须进文件日志；控制台只显示友好摘要。

## 7. 工程可维护性（必须）

- **幂等优先（Idempotent）**：工具尽量幂等，重复执行不造成不可逆损害。
- **资源上限**：输出/读取/日志必须有上限（bytes/lines/timeout），避免 UI/内存被打爆。

## 8. 协作与版本（推荐）

- **提交规范**：建议 `feat:` / `fix:` / `refactor:`。
- **变更记录**：对外可见行为变更必须更新 `README/docs`。

## 9. UI 与可视化（必须）

### 9.1 Live UI 布局（推荐）
- Live 界面固定布局：架构流向、状态机、思考滚动、操作信息。

### 9.2 多模式 UI 输出一致性（UI Output Consistency）

> **核心原则**：classic/enhanced/opencode 三种模式展示的核心信息必须语义一致。

| 规范项 | 说明 |
|--------|------|
| **输出内容同源** | 系统提示词/用户提示词、LLM 请求/响应、工具调用/结果必须在所有 UI 中可见。 |
| **事件处理对齐** | 新增事件必须同步实现三种 UI 的渲染。 |
| **颜色语义统一** | system/user/assistant/error/warning/success 颜色语义一致。 |

## 10. 文档质量门禁（必须）

- 文档出现英文术语必须带中文解释。
- 文档必须可读、可执行、可验收（包含检查清单/示例/路径）。

## 11. 规范演进（推荐）

- 优先补齐：自动化质量门禁、依赖锁定、资源上限策略、回放与诊断工具链。

