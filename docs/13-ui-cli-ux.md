# 13｜CLI/交互 UX（Streaming / Confirmations / 可读性）

目标：让用户“看得懂、控得住、可追溯”，并减少误操作。

## 1. 交互原则
- 默认先给**计划**，再执行
- 工具调用必须可见（可折叠），并显示影响面（哪些文件/命令）
- 危险动作必须确认（写/删/执行/网络/git push）

## 2. CLI 信息架构（建议）

### 2.1 输出区域
- **对话输出**：模型的自然语言解释
- **工具日志**：每次 tool call 的 name/args 摘要/结果
- **变更预览**：diff/文件列表/统计
- **验证结果**：test/lint/build 的摘要 + 失败定位

### 2.2 关键交互点
- `confirm`：展示风险与范围（single/session/workspace）
- `cancel`：停止当前步骤（并提示是否回滚）
- `resume`：断点续跑（加载 plan + 已完成步骤）

## 3. 流式输出（Streaming）
- 逐 token 输出，但在遇到工具调用时：
  - 先“收束”当前解释段落
  - 再展示工具调用卡片（参数摘要）
  - 工具返回后再继续解释

## 4. 错误展示与建议
- 把错误分为：
  - 可自动修复（提示将进行修复）
  - 需要用户协助（给出具体命令/操作）
- 保留 `trace_id` 方便排查

## 5. 可配置项（建议）
- 输出语言/简洁度
- 默认验证策略（lint/test/build）
- 是否允许后台任务
- 是否显示完整工具参数（默认摘要）

## 6. Live UI：`opencode` / `enhanced` 的“对话/输出”窗格规范（可验收）

> 适用范围：`clude chat --live --live-ui opencode` 的 `对话/输出` 窗格（Textual 多窗格滚动），以及 `enhanced` UI 的主输出区。
>
> 目的：把一次 turn 的“执行逻辑 + 关键推理/决策 + 可追溯证据”讲清楚，且能支持排障（与 `audit.jsonl` / `trace_id` 对齐）。

### 6.1 总体目标（必须同时满足）
- **可读**：非开发者也能顺着读懂“发生了什么/为什么/接下来做什么”。
- **可排障**：开发者能从同一窗格快速定位异常（哪一步/哪次 tool/哪个 trace_id）。
- **不泄露**：默认脱敏（API Key/Token/本地路径敏感段/过长日志截断）。
- **不噪音**：默认只输出“摘要 + 关键证据”；详细原始 JSON 走 `事件`/`操作面板`，或通过开关显示。

### 6.2 信息层级（从上到下的叙事顺序）
同一轮 turn 内，“对话/输出”应按如下层级输出（允许缺省，但顺序建议一致）：
- **(A) 系统上下文块**：一次性信息（如：项目记忆加载、会话恢复、策略开关）。启动时只显示一次。
- **(B) 用户输入块**：原始 user message（不修改、不重排）。
- **(C) 代理过程块（关键）**：用 1–3 段话说明本轮的**决策/思路**（例如：为何进入 planning、为何 fallback、为何选择某工具/策略）。
- **(D) 执行轨迹块**：按 step/阶段输出“做了什么”的摘要（工具调用、读写影响面、验证结果）。
- **(E) 结论块**：最终回答/下一步建议（必要时附“已完成/未完成/风险”）。

### 6.3 块（Block）结构：统一外观与可检索标签
建议统一为“带头部的块”，便于用户滚动浏览与 grep/搜索：
- **块头部（单行）**：`[time] [LEVEL] [STEP] [EV] [trace_id] 标题`
  - **time**：本地时间（可选，但建议在 debug/排障模式开启）
  - **LEVEL**：`INFO / PROGRESS / WARN / ERROR / SUCCESS`
  - **STEP**：`step=29` 或 `step=-`（无 step 也要明确）
  - **EV**：事件名或语义标签（如 `llm_request_params` / `tool_call` / `verify`）
  - **trace_id**：可选但强烈建议（至少在 WARN/ERROR 输出）
- **块正文（多行）**：
  - 第一段 **Summary**：最多 3 行，说明“发生了什么”
  - 第二段 **Why/Decision**：可选，说明“为什么这样做/权衡”
  - 第三段 **Evidence**：可选，列关键证据（文件路径/命令/工具名/错误码），避免整段 JSON
- **块尾部（可选）**：`(truncated)`、`(details in 事件/操作面板)`、`(see audit.jsonl)` 等提示

### 6.4 事件 → “对话/输出”展示映射（摘要优先）
下面规定：哪些事件必须在 `对话/输出` 出现、出现成什么块；其余细节留给 `事件` 或 `操作面板`：
- **项目记忆加载**（startup）：
  - **必须**：展示一次 `项目记忆已加载（CLUDE.md）`（含 path/length/truncated/legacy_name 摘要）
  - **禁止**：用户每次输入后重复展示
- **user_message**：
  - **必须**：用户输入原文（可蓝色高亮）
- **display（工具）**：
  - **必须**：按 `level` 显示为过程块（progress/info/warn/error/success），用于“阶段提示/中间结论/解释”
  - **建议**：支持 `scope` 或 `step_id`，便于归档到当前 step
- **plan_generated / plan_step_start / plan_step_end**：
  - **必须**：以“执行轨迹块”展示计划与当前步（标题 + 1 行摘要）
  - **建议**：只在 plan 变更时输出完整 steps（避免每次重绘重复）
- **llm_request_params**：
  - **建议**：在 `对话/输出` 只输出“LLM 请求摘要”（model/api_mode/base_url/prompt_tokens_est/max_tokens/temperature），不输出 messages 原文
  - **必须**：若发生 WARN/ERROR（例如超时/重试），输出 trace_id 与重试策略摘要
- **tool_call_parsed**：
  - **必须**：输出 `Tool: <name>` + args 摘要（按工具类型挑关键字段；避免 dump 全量）
  - **必须**：标出策略影响（是否需要 confirm、是否被 policy 拦截）
  - **建议**：对 file-write/exec/network 工具输出“影响面”（文件/命令/域名）
- **tool_result**：
  - **必须**：输出结果摘要：`✓/✗`、错误码（若有）、受影响文件/行数/输出截断提示
  - **建议**：将“长输出/原始 JSON”放到 `操作面板` 或 `事件`，对话区只给 3–10 行关键摘录
- **llm_usage**：
  - **不强制**：一般放 `clude chat` 顶栏（Context/Output/TPS）
  - **但**：若出现异常（Context=0、TPS=0 持续等），在 `对话/输出` 给出诊断提示块（含建议下一步）
- **assistant_text（最终回答）**：
  - **必须**：输出最终答复；若本轮回答很短或为空，需要在 UI 上提示“模型输出异常/已 fallback 文本”

### 6.5 可读性与排障能力（硬性要求）
- **可定位**：任何 WARN/ERROR 块必须包含：
  - **trace_id**（若存在）与 **step_id**
  - **错误码**（如 `E_DEP_MISSING/E_POLICY/E_INVALID_ARGS/E_TIMEOUT`）
  - **下一步建议**（用户可执行命令或打开的文件）
- **可检索**：块头部必须包含一致的 `EV=` 或事件名关键字，方便用户复制/搜索。
- **可复制**：对话区内容应尽量“纯文本友好”（避免只靠颜色表达关键信息）。

### 6.6 脱敏与截断（默认开启）
- **脱敏**：API key/token/Authorization 头、可能的私密路径片段应替换为 `***`。
- **截断**：单块正文超过阈值（例如 2000–4000 字）必须截断并标记 `(truncated)`。
- **二次定位**：截断时给出“详情位置”（例如：`见 事件 窗格 / .clude/logs/audit.jsonl`）。

### 6.7 可配置的“详细度档位”（建议）
至少三档（可由 CLI flag 或 slash command 切换）：
- **compact（默认）**：只输出 C/D/E 的摘要块
- **verbose**：额外输出关键 args 摘要、更多 evidence
- **debug**：对话区也允许输出原始片段（仍需脱敏/截断），并强制 time/trace_id

### 6.8 验收用例（你可据此肉眼验收）
- **用例 1：只问一句话**：启动显示一次项目记忆块 → user → 代理过程块（1 段）→ assistant。
- **用例 2：触发工具链**：user → 代理过程块（说明为何需要读文件）→ tool_call/read_file 摘要 → tool_result 摘要 → assistant（引用证据）。
- **用例 3：策略拦截**：tool_call → 输出“被 policy 拦截”的 ERROR 块（含 trace_id/错误码/如何解除）。
- **用例 4：LLM 输出异常**：assistant_text 为空或全是换行 → 输出 WARN 块（说明 fallback）→ 给出下一步诊断建议。


