## websearch / codesearch（`src/clude_code/tooling/tools/search.py`）业界优化点

### 当前模块职责

- **websearch**：通过 provider 列表（Open-WebSearch MCP 优先，失败回退 Serper）获取搜索结果，做结构归一化。
- **codesearch**：通过 Grep.app 做网络代码搜索（带轻量重试、非 JSON 处理、预算截断）。

### 业界技术原理

- **Provider fallback**：把外部服务当作不稳定依赖，必须有优雅降级（配置缺失/限流/5xx）。
- **结构归一化（normalize）**：把不同 provider 的字段归一为 `title/url/snippet`，避免上层消费逻辑分叉。
- **预算控制**：搜索结果必须限制条数与 snippet 长度，并在回喂时进一步压缩。

### 现状评估（本项目）

- 已实现：provider 列表回退；结果归一化；Grep.app 轻量重试与预算截断；provider 字段补齐。

### 可优化点（建议优先级）

- **P1：统一重试与超时策略**
  - **原理**：不同 provider 的重试/超时不一致会造成尾延迟不可控。
  - **建议**：抽出 `http_client` helper：统一 timeout/backoff/jitter，按 429/5xx 分类重试。

- **P1：把“搜索→抓取”形成工具链提示（toolchain hints）**
  - **原理**：业界会显式教模型先 websearch 再 webfetch，减少误抓全文与无效请求。
  - **建议**：ToolSpec.description 里增加组合用法与注意事项（避免重复/避免抓取大 PDF）。


