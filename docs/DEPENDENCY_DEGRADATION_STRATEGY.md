# 风险与降级策略（实现思路 + 落地清单）

> 依据：`docs/AGENT_DESIGN_ENTERPRISE_FEASIBILITY_REPORT.md` L229-L237  
> 目标：把“失败场景 → 降级策略”变成**可实现、可验证、可审计**的工程闭环。

---

## 1) LLM API（超时 / 限流 / 服务不可用）

### 触发条件
- `httpx.TimeoutException` / `httpx.RequestError`
- HTTP 429 / 502 / 503 / 504
- 响应格式异常（choices/message 缺失）

### 降级策略（实现）
- **指数退避重试**：2~3 次（例如 0.5s, 1s, 2s + jitter）
- **保存上下文**：失败时写入 `audit`/`trace` 事件（不写敏感明文；依赖 audit 脱敏）
  - event: `llm_call_failed`
  - data: stage/step_id/base_url/model/messages_count/last_user_preview/error_code
- **用户可理解的失败提示**：返回“服务暂时不可用，请稍后重试/切换模型/检查网络”，同时保留 trace_id 便于排查

### 未来增强（不阻塞 MVP）
- 自动切换备用模型/备用 base_url（ModelRouter + 多 provider）
- 失败时持久化“本轮 messages 摘要快照”（可选加密）

---

## 2) Grep.app（代码搜索）网络故障 / API 变更

### 触发条件
- 网络错误（连接/超时）
- HTTP >= 400
- 解析失败 / 返回结构变更
- 结果为空（`E_NO_RESULTS`）

### 降级策略（实现）
- **回退到本地 ripgrep**：
  - 使用现有 `grep` 工具（rg 优先，Python fallback）
  - 输出仍保持 `codesearch` 的 `query/results/total_results` 契约
  - 标注：`payload.provider="local_ripgrep_fallback"`，并附 `fallback_from="grep_app"` 供 UI/日志识别

### 未来增强（不阻塞 MVP）
- Grep.app + 本地 ripgrep 的结果融合与去重（rank）

---

## 3) Serper/WebSearch（API Key 失效 / 限流）

### 触发条件
- API Key 缺失（E_NOT_CONFIGURED）
- HTTP 429 / 5xx / 网络错误
- 全 providers 失败

### 降级策略（实现）
- **回退缓存结果**：
  - 成功搜索后写入缓存（按 query key，带 ttl）
  - provider 全失败时尝试从缓存命中返回：`provider="cache"`、`cache_hit=true`
- 若无缓存：返回明确提示 **“请手动提供链接或关键词”**

---

## 4) Git（沙箱 worktree）非 Git 仓库 / 权限不足

### 触发条件
- 非 git repo、git 不可用、worktree add/remove 失败

### 降级策略（实现）
- **回退 temp copy + 合并回放**
  - 已实现：SandboxRunner worktree 优先，否则 copy
  - 失败：丢弃沙箱目录，主 workspace 不污染

---

## 5) fastembed（向量索引）依赖缺失

### 触发条件
- `fastembed` import 失败

### 降级策略（实现）
- **禁用语义搜索，仅用 ripgrep 词法搜索**
  - 已实现：IndexerService 缺依赖时禁用并仅打印一次 warning

---

## 6) 落地检查清单（MVP）

- [ ] LLM：重试 + 失败落 audit/trace + 友好提示
- [ ] codesearch：grep.app 失败 → 本地 ripgrep fallback（契约不变）
- [ ] websearch：provider 全失败 → cache fallback / 提示用户
- [ ] smoke：断网/无 key/无 git/无 fastembed 均不崩溃


