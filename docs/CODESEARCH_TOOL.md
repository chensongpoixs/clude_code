## codesearch 工具功能文档（Code Search Tool）

### 1. codesearch 是干嘛的（What & Why）

`codesearch` 的定位是：**为“编程/改代码”任务检索可直接复用的代码上下文（Code Context）**，把“散落在仓库/互联网上的实现示例、用法片段、最佳实践”以结构化结果返回给 Agent，供 LLM 快速决策与生成补丁。

它与 `websearch` 的差异（Industry Split）：
- **websearch（网页搜索）**：面向“实时资料/新闻/文档/网页内容”，返回网页摘要与链接。
- **codesearch（代码搜索）**：面向“代码实现片段”，返回**代码块（code）+ 语言（language）+ 解释（explanation）+ 相关度（relevance_score）**，更适合“我需要怎么写/怎么调用某 API/某框架最佳实践”的场景。

### 2. 当前项目内的真实状态（Current State）

在本项目中，`src/clude_code/tooling/tools/search.py` 的 `codesearch()` 目前是 **mock 占位实现**：
- 不做真实网络/本地检索；
- 固定返回两条示例（python/js），用于打通工具链、UI 渲染、反馈格式等。

工具调用链（Call Chain）：
- `tool_dispatch.py` 中注册了 ToolSpec：`name="codesearch"`，参数为 `query` 与 `tokens_num`
- 运行时由 `AgentLoop -> dispatch_tool -> loop.tools.codesearch()` 调到 `LocalTools.codesearch()`，最终落到 `tooling/tools/search.py::codesearch()`

### 3. 输入与输出契约（I/O Contract）

#### 3.1 输入参数（Inputs）
- **query**：代码搜索查询（自然语言/关键词/函数名/报错栈/库名均可）
- **tokens_num**：期望返回的“内容规模预算”（Budget），用于控制返回长度（业界常用：把 budget 当作输出上限，而不是强保证）

#### 3.2 输出结构（Outputs）
返回 `ToolResult(ok=True, payload=...)`，payload 建议稳定包含：
- **query**：原始 query
- **results**：代码结果列表，每项建议包含：
  - `language`：语言（python/js/ts/go…）
  - `code`：代码片段（可直接拷贝/可运行/可改造）
  - `explanation`：解释说明（中文为主，英文术语必须带中文解释）
  - `relevance_score`：相关度评分（0-1 或 0-100，保持一致即可）
- **tokens_used / total_available**：预算与实际使用（可近似估算）

> 注意：`codesearch` 返回的 `code` 片段应被视为**不可信输入（Untrusted Input）**，必须通过后续验证（lint/tests/最小复现）再落盘。

### 4. 业界实现方式（Industry Implementations）

`codesearch` 在业界常见有两条落地路线，项目可二选一或混合：

#### 4.1 本地代码检索（Local Search / RAG）
- **语义检索（Semantic Search）**：对仓库做 embedding，按 query 召回相似代码块（RAG：Retrieval-Augmented Generation，检索增强生成）
- **符号/结构检索（Symbol/AST Search）**：基于 tree-sitter/ctags/LSIF，按函数名、类名、调用关系检索
- 优点：不依赖外网；隐私更可控；对当前仓库改动更精准
- 缺点：需要索引与增量更新；需要处理 chunk 粒度与召回质量

#### 4.2 外部代码搜索服务（External Code Search API）
典型能力包括：
- 全网开源代码搜索（按关键字/语义/语言过滤）
- 返回高质量示例（尤其是热门框架与 SDK 用法）

业界注意事项：
- **许可（License）**：返回片段可能带许可证约束，需在落地前提醒/确认
- **注入风险（Prompt Injection）**：代码/README 可能包含恶意指令，不可直接信任
- **敏感信息（Secrets）**：禁止把本地私有代码/密钥发到外部服务

### 5. 使用场景建议（When to Use）

优先使用 `codesearch` 的场景：
- 需要“某库/某框架的典型写法、最佳实践、最小示例”
- 需要“某报错的常见修复方式（带代码）”
- 需要“对比几种实现方式（不同语言/不同范式）”

不建议用 `codesearch` 的场景：
- 只需要读取仓库已有代码（用 `read_file/grep/search_semantic` 更合适）
- 只需要查实时资料/官网文档（用 `websearch/webfetch` 更合适）

### 6. 安全与健壮性要求（Security & Robustness）

- **资源上限**：必须限制返回大小（tokens/字符/条数），避免 UI 与上下文被打爆
- **脱敏**：日志与输出不得包含 API Key、Token、Cookie 等敏感字段
- **失败降级**：外部 provider 失败时应返回明确 error code（如 `E_NOT_CONFIGURED/E_PROVIDER_FAILED`）
- **可回放**：建议在文件日志里记录 provider、耗时、结果条数（但不记录明文密钥）

### 7. 本项目当前实现（仅网络搜索：Grep.app）

按你的要求，本项目的 `codesearch` **只实现网络代码搜索**（Grep.app），不提供 `local_rag` 本地检索与回退。

- **Grep.app（Network Code Search）**：
  - 配置项：`search.grep_app_enabled / search.grep_app_base_url / search.grep_app_endpoint`
  - 请求方式：`GET {base_url}{endpoint}?q=...`
  - 返回：统一转换为 `results[]`（含 `repo/path/language/code/url`），并限制结果条数与内容预算避免刷屏


