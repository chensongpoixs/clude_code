## 工具实现程度与规范对齐状态（Tooling Implementation Status）

> 目的：对照项目代码规范，记录各工具的“实现程度 / 健壮性 / 提示词优化 / 回喂压缩（feedback）”状态，便于验收与持续演进。

> 补充：各工具模块的**业界对齐原理与优化点**已按模块沉淀在：`docs/TOOLING_INDUSTRY_OPTIMIZATION_INDEX.md`

### 核心判定维度

- **实现程度**：是否可用、是否依赖可选库、是否有清晰错误码
- **健壮性**：网络超时/重试、返回结构容错、输出上限、异常降级
- **提示词优化**：`ToolSpec.summary/description/example_args` 是否明确“何时用/何时不用”
- **回喂压缩**：`tooling/feedback.py` 是否回喂摘要，避免把大 payload 原样塞回模型

### 状态总览（摘要）

| 工具 | 实现程度 | 健壮性 | 提示词 | 回喂压缩 | 备注 |
|------|----------|--------|--------|----------|------|
| **codesearch** | ✅ Grep.app | ✅ | ✅ | ✅ | 网络代码搜索；含重试、非 JSON 处理、结构容错 |
| **websearch** | ✅ MCP/Serper | ⚠️（基础） | ✅ | ✅ | provider 回退已实现；后续可补 HTTP/JSON 重试一致性 |
| **webfetch** | ✅ httpx | ✅ | ✅ | ✅ | 去除 requests 依赖；http/https 校验；截断按配置 |
| **run_cmd** | ✅ | ✅（新增超时） | ✅ | ✅（已有） | 新增 timeout_s（默认取 command.timeout_s） |
| **read_file** | ✅ | ✅ | ✅ | ✅ | 支持 offset/limit；回喂为语义窗口采样摘要 |
| **grep** | ✅ | ✅（极致稳健） | ✅ | ✅ | 优先 rg，回退 python；**实时读取 stdout 且强制截断进程**；支持 language/glob |
| **list_dir** | ✅ | ✅ | ✅ | ✅ | 回喂仅前 20 项摘要 |
| **glob_file_search** | ✅ | ✅ | ✅ | ✅ | 回喂仅前 50 个匹配 |
| **apply_patch** | ✅ | ✅ | ✅ | ✅ | 回喂字段为 hash/undo_id 等高信号信息 |
| **undo_patch** | ✅ | ✅ | ✅ | ✅ | 回喂字段为 restored_hash 等高信号信息 |
| **write_file** | ✅ | ✅ | ✅ | ✅ | 回喂仅 path/action/bytes_written（避免回传正文） |
| **search_semantic** | ✅ LanceDB | ✅ | ✅ | ✅ | 支持 RAG 语义搜索；缺少依赖时自动禁用并降级 |

> 说明：表中未列出的工具（read_file/grep/list_dir/apply_patch 等）属于本地工具，核心关注点是“输出上限/参数校验/回喂压缩”，后续可按同一模板继续补齐。

### 近期已对齐的关键改动点

- **grep（极致稳健性增强）**
  - **健壮性**：重构为 `Popen` 实时读取 `rg --json` 输出；一旦达到 `max_hits` 立即 `terminate()` 搜索进程（防止超大项目进程过载）；`stderr` 完整捕获。
  - **功能对齐**：Python fallback 路径同步支持了 `language`（自动后缀匹配）与 `include_glob` 参数。
  - **回喂**：严格执行 `MAX_GREP_HITS`（20 条）摘要回喂，防止上下文爆炸。

- **codesearch（Grep.app）**
  - **健壮性**：URL 校验、2 次重试（429/5xx）、非 JSON 响应处理、返回结构容错（hits.hits）
  - **提示词**：ToolSpec 明确适用/不适用场景与 query 示例
  - **回喂**：只回喂前 5 条的 repo/path/language/preview/url

- **webfetch**
  - **实现程度**：改为 `httpx`，不再依赖 `requests`
  - **健壮性**：仅允许 http/https、follow_redirects、429/5xx 轻量重试、按 `web.max_content_length` 截断
  - **提示词**：ToolSpec 增加“建议先 websearch 再 webfetch”的组合用法
  - **回喂**：仅回喂 content_preview（前 800 字符）+ 元信息

- **websearch**
  - **提示词**：ToolSpec 增加“websearch 找页面、webfetch 抓全文”的组合用法
  - **回喂**：只回喂前 5 条 title/url/snippet 摘要

- **run_cmd**
  - **健壮性**：新增 `timeout_s` 参数，并在工具实现层用 `subprocess.run(timeout=...)` 强制超时
  - **提示词**：ToolSpec 增加风险提示（副作用、需遵守 policy）

- **本地工具（read_file/grep/apply_patch/write_file 等）**
  - **提示词**：ToolSpec 统一补充“适用/不适用/注意事项/示例”，减少模型误用
  - **回喂**：统一走摘要回喂（避免把大 payload 原样塞回 messages）


