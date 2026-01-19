# Clude Code 工业级代码工程规范

> 目的：这份规范用于**强制统一工程质量**。后续每次实现/改动代码时，都应先对照此文档做“设计前检查 + 提交前检查”。  
> 范围：Python 纯 CLI Code Agent（含 LLM、Tooling、Verification、Observability、Docs）。

## 1. 核心准则
- **函数长度控制**：单函数代码行数限制在 200 行以内。超出必须拆分为功能函数。
- **逻辑简单化**：主函数（如 `run_turn`）仅包含逻辑调度，具体实现下沉到私有方法。
- **中文注释**：所有代码必须包含详尽的中文文档字符串（Docstrings）和关键逻辑注释。

## 2. 规范使用流程（每次写代码都要走）
- **设计前检查（Before Coding）**：
  - 明确改动属于哪一层：`orchestrator` / `tooling` / `llm` / `verification` / `observability` / `docs`
  - 明确数据契约：是否新增/变更 JSON Schema / Pydantic Model
  - 明确安全影响：是否涉及写文件/执行命令/网络访问（Policy & Confirm）
- **提交前检查（Before Commit）**：
  - 通过格式化/静态检查（见“质量门禁”）
  - 通过最小验证集（lint/test/验证闭环）
  - 日志：控制台不泄露敏感信息；文件日志可复现问题

## 3. 架构与模块化规范
- **文件容量硬限制**：**单个 Python 文件不得超过 2000 行**。
- **抗膨胀策略**：
    - 当文件接近 1500 行时，应启动重构预警。
    - **组件抽离**：将大类中的独立功能（如日志管理、策略检查）抽离为独立文件中的独立类。
    - **目录化方案**：当 `module.py` 过大，将其转换为 `module/` 文件夹，主入口保留在 `__init__.py` 或 `main.py`。
- **解耦设计**：编排层 (Orchestrator) 不得直接包含工具实现细节。
- **注册表模式**：不断增长的组件（如 Tooling）必须采用插件/注册表模式，禁止在单文件中线性堆叠。
- **协议驱动**：所有 LLM 交互和工具调用必须符合定义好的 JSON Schema。
- **状态机管理**：Agent 行为必须受显式状态机（AgentState）驱动，禁止隐式黑盒跳转。

### 3.1 模块配置统一管理（Configuration Centralization）

> **核心原则**：所有模块的可配置参数必须统一纳入全局配置体系（`src/clude_code/config/`），禁止模块内硬编码或自行管理配置。

| 规范项 | 说明 |
|--------|------|
| **配置集中化** | 新增模块的配置项必须在 `src/clude_code/config/config.py` 中定义对应的 Pydantic `BaseModel` 子类，并挂载到 `CludeConfig`。工具类配置统一在 `src/clude_code/config/tools_config.py` 定义，并通过 `set_tool_configs(cfg)` 注入。 |
| **配置优先级** | 统一遵循：`环境变量 > 配置文件 > 代码默认值`。实现必须使用 `pydantic-settings` 的 `settings_customise_sources`，禁止通过 `__init__` 人工合并导致优先级反转。 |
| **嵌套环境变量** | 必须启用 `env_nested_delimiter="__"`，确保 `CLUDE_LLM__MAX_TOKENS`、`CLUDE_POLICY__ALLOW_NETWORK` 等嵌套配置可被正确解析。 |
| **敏感信息脱敏** | API Key、Token 等敏感配置项禁止硬编码；必须通过环境变量或配置文件注入，且在日志中脱敏显示。 |
| **配置注入时机** | 模块配置应在 `AgentLoop.__init__` 或模块初始化阶段统一注入，避免运行时动态读取环境变量。 |
| **配置文档化** | 新增配置项必须在 `.clude/.clude.example.yaml` 中补充示例，并在对应模块 README 或 `docs/` 中说明用途与取值范围。 |

**标准配置类模板**：
```python
class XxxConfig(BaseModel):
    """模块 Xxx 配置"""
    enabled: bool = Field(default=True, description="是否启用该模块")
    api_key: str = Field(default="", description="API Key（环境变量优先）")
    timeout_s: int = Field(default=10, ge=1, le=60, description="请求超时时间")
    # ... 其他配置项
```

**配置注入示例**：
```python
# 在 AgentLoop.__init__ 中
from xxx_module import set_xxx_config
set_xxx_config(cfg)  # cfg: CludeConfig
```

**实现检查清单**（新增模块配置时必须逐项确认）：
- [ ] `config.py`：定义 `XxxConfig` 并添加到 `CludeConfig`
- [ ] 模块内：提供 `set_xxx_config()` 或构造函数接收配置
- [ ] `AgentLoop.__init__`：调用配置注入
- [ ] `.clude/.clude.example.yaml`：补充配置示例
- [ ] 模块文档：说明配置项含义与取值

### 3.2 配置文件格式、位置与生成规则（YAML + Commented Template）

> **目标**：让配置“可读、可迁移、可审计、可复现”，并确保配置在不同运行环境下行为一致。

| 规范项 | 说明 |
|--------|------|
| **格式统一** | 配置文件统一使用 **YAML**，禁止新增 JSON 配置文件作为主配置来源（历史 JSON 仅允许读取兼容，不作为默认输出）。 |
| **主配置位置** | 主配置文件固定为：`~/.clude/.clude.yaml`。该文件是“可编辑配置”的唯一落盘位置。 |
| **兼容读取顺序** | 允许兼容读取：工作区 `./.clude/.clude.yaml`（用于旧项目/脚本兼容）、`./clude.yaml`（向后兼容）。但**生成/保存**必须写入 `~/.clude/.clude.yaml`。 |
| **注释保留** | 生成/保存 YAML 时必须保留中文注释：以 `.clude/.clude.example.yaml` 作为模板进行“按路径替换值”，禁止直接 `yaml.safe_dump()` 导致注释丢失。 |
| **顺序一致** | 生成/保存 YAML 的顶层 key 顺序必须与 `.clude/.clude.example.yaml` 一致（提高可读性、便于 diff）。 |
| **默认值来源** | 当需要“生成默认配置”时，默认值必须来自 **代码默认配置**（Pydantic 字段默认值），不得被环境变量或已有配置文件污染。推荐使用 `model_construct()` 生成纯默认对象。 |
| **敏感字段示例** | `.clude/.clude.example.yaml` 中禁止提交真实 API Key/Token；必须使用空字符串或占位符，并在注释中说明推荐使用环境变量。 |

**实现检查清单**（配置生成/保存必须逐项确认）：
- [ ] 保存目标路径为 `~/.clude/.clude.yaml`
- [ ] 使用模板渲染（保留中文注释、顺序）
- [ ] “生成默认配置”使用代码默认值（不受 env/file 影响）
- [ ] env 覆盖 file：`env_nested_delimiter="__"` 生效且有验证用例

### 3.3 工具配置与日志标准化（Tool Config + Tool Logger）

> **目标**：每个工具都有明确的“开关/日志策略/参数边界”，出现问题能快速定位、可复现、可审计。

| 规范项 | 说明 |
|--------|------|
| **工具独立配置** | 每个工具必须有独立配置条目（例如 `FileToolConfig`、`CommandToolConfig`、`WeatherToolConfig`），至少包含：`enabled`、`log_to_file`（如适用）。统一定义在 `src/clude_code/config/tools_config.py`。 |
| **新增工具默认配置必备** | 每新增一个工具，必须在全局 `ToolConfigs` 中增加该工具的配置字段并提供默认值（即“开箱即用”的默认配置）。禁止出现“工具已注册但没有全局默认配置项”的情况。 |
| **统一注入** | 工具配置必须通过 `set_tool_configs(cfg)` 注入，并由 `get_tool_configs()` 读取；禁止工具模块自行从文件/环境变量直接读配置。 |
| **统一日志初始化** | 所有工具模块必须使用统一的工具日志助手（例如 `src/clude_code/tooling/logger_helper.py`），确保遵循全局 `LoggingConfig`（级别、滚动、格式）与工具自身 `log_to_file` 开关。 |
| **错误反馈** | 工具错误必须提供可操作信息（配置缺失、鉴权失败、网络异常等），并保证敏感信息不出现在控制台/日志明文中。 |

**实现检查清单**（新增工具时必须逐项确认）：
- [ ] `ToolSpec`：工具的 `name/description/args_schema/example_args` 完整（工具注册表单一可信源）
- [ ] `src/clude_code/config/tools_config.py`：新增 `XxxToolConfig`（至少 `enabled`、`log_to_file`）
- [ ] `ToolConfigs`：新增字段 `xxx: XxxToolConfig = Field(default_factory=XxxToolConfig)` 或等价默认挂载
- [ ] `.clude/.clude.example.yaml`：新增同名段落与中文注释（并确保模板渲染可替换该路径的值）
- [ ] 工具实现：启动时读取 `get_tool_configs().xxx` 并尊重 `enabled/log_to_file`
- [ ] `set_tool_configs(cfg)`：在 `AgentLoop` 初始化阶段完成注入，保证运行期配置一致

## 4. 日志与调试
- **禁止 print**：使用系统 logger。
- **控制台日志**：追求美观简洁（Rich 格式），只显示关键路径。
- **文件日志**：包含文件名、行号，记录完整上下文和原始 JSON，用于问题回溯。
- **审计追踪**：记录每一步的操作 Hash 和 Trace ID。

## 5. 质量门禁（业界缺口重点补齐）
- **格式化/风格**：统一 formatter（建议 `ruff format` 或 `black` 二选一），禁止“局部风格”。
- **静态检查**：建议最少包含 `ruff`（lint）+ `mypy`（类型）+ `pydantic` 校验（运行时）。
- **测试与验证**：
  - 单元测试：关键解析/规范化/策略判断必须可测（尤其是 message normalization、policy、patch/rollback）。
  - 集成验证：Verification 闭环必须可在本机一键运行（CLI doctor / verify）。
- **变更影响控制**：任何会影响 LLM 输入输出契约的改动（prompt、schema、tool feedback）必须更新文档与示例。

### 5.1 本项目落地约定（可执行入口）
- **依赖安装（开发态）**：`pip install -e ".[dev]"`
- **格式化**：`ruff format .`
- **Lint（代码静态检查）**：`ruff check .`
- **类型检查**：`mypy src`
- **pre-commit**：`pre-commit install`（提交前自动跑 ruff/mypy）
- **CI**：`.github/workflows/ci.yml` 会在 PR/Push 自动执行 lint/format/type/test（如存在 tests/）

## 6. 安全与稳健性（业界缺口重点补齐）
- **决策门拦截**：写操作和执行操作必须经过用户确认 (HITL)。
- **命令黑名单**：严禁执行高危系统指令。
- **自愈闭环**：代码改动后自动触发 Verifier，错误信息必须结构化回喂给 LLM 修复。

### 6.1 安全补充条款
- **最小权限**：默认 `allow_network=False`，需要网络必须显式开关且被审计记录。 
- **可执行命令白名单优先**：黑名单只是底线，推荐逐步演进到“白名单 + 参数约束”。

## 7. 工程可维护性（业界规范 & 本项目强化）
- **错误处理**：所有异常必须写入 file-only 日志；控制台只显示友好摘要，避免污染 Live UI。
- **边界与幂等**：工具层函数尽量幂等；重复执行不会造成不可逆损害（尤其 patch/undo/写文件）。
- **资源与性能**： 对大型文件/日志输出设置上限（bytes/lines）。

## 8. 协作与版本（业界工程常见缺口）
- **提交规范**：建议采用简化版 Conventional Commits（如 `feat:`, `fix:`, `refactor:`）。
- **变更记录**：对外可见行为变更必须更新 `README`/`docs`。
- **兼容性**：对 Python 版本、依赖版本要有明确约束（requirements/lock）。

## 9. UI 与可视化

### 9.1 界面布局规范
- **Live 界面**：固定 50 行布局，包含架构流向、状态机、思考滚动、操作信息。
- **SVG 流程图**：重要逻辑模块必须有对应的带 CSS 动画的 SVG 流程图。

### 9.2 多模式 UI 输出一致性（UI Output Consistency）

> **核心原则**：无论用户选择哪种 UI 模式，其看到的核心信息内容必须保持语义一致，确保调试体验和信息透明度统一。

| 规范项 | 说明 |
|--------|------|
| **输出内容同源** | `clude chat`（classic/enhanced）与 `opencode` TUI 的"对话/输出"窗口必须显示相同的核心事件信息（系统提示词、用户提示词、LLM 请求/响应、工具调用/结果等）。 |
| **事件处理对齐** | 新增事件类型时，必须同时在 `live_view.py`（classic）、`enhanced_live_view.py`（enhanced）、`opencode_tui.py`（opencode）三处实现对应的显示逻辑。 |
| **颜色语义统一** | 不同角色/状态使用统一的颜色语义：`system=magenta`、`user=green`、`assistant=blue`、`error=red`、`success=green`、`warning=yellow`。 |
| **信息完整性** | LLM 请求时必须显示完整的 messages 内容（系统提示词 + 用户提示词），便于调试和问题定位。 |
| **格式可读性** | 使用结构化格式展示复杂内容（如 JSON、多行文本），包含角色标识、内容长度、分隔线等视觉辅助元素。 |

**实现检查清单**（新增事件时必须逐项确认）：
- [ ] `llm_io.py` 或对应事件源：事件数据包含完整信息
- [ ] `live_view.py`：classic 模式显示逻辑
- [ ] `enhanced_live_view.py`：enhanced 模式显示逻辑
- [ ] `opencode_tui.py`：opencode TUI 模式显示逻辑
- [ ] 三种模式输出的核心信息语义一致

## 10. 文档质量门禁 (Documentation Quality)
- **双语注释强制化**：所有文档中包含英文的技术名词或标题，必须紧随其后的括号中或以其他形式提供中文注释。
- **自动化校验**：在提交文档前，必须通过 `python tools/check_docs_bilingual.py` 的校验（0 错误）。
- **链接有效性**：必须通过 `python tools/check_doc_links.py` 校验，禁止出现死链或空链接。

## 11. 业界对比与规范演进（Industry Comparison）

### 11.1 当前规范的优势
- **已有强项**：行数硬限制、显式状态机、日志分层、审计追踪、HITL 确认机制、SVG 可视化、多模式 UI 一致性。

### 11.2 持续补齐方向
- **业界常见但需持续强化**：质量门禁自动化（formatter/lint/type/test）、协作/版本规范策略、资源上限与截断策略、依赖版本锁定。
- **落地建议**：通过 CI（GitHub Actions）与 pre-commit 钩子自动化执行规范检查。

