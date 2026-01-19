# 控制协议“鬼打墙”复盘与修复方案（V2）

> 目标：解释为什么出现 `{"control":"step_done"}` 被当成“最终回复”的现象，并给出**可落地**的修复方案与代码改动点。

---

## 1. 现象复述（基于日志事实）

日志显示：
- 业务上已经完成了天气查询（有 `get_weather` 调用与 `display` 输出）。
- 之后 LLM 在某些轮次直接返回：
  - `{"control": "step_done"}\n\n{"control": "step_done"}`
- `react.py` 在 **tool_call 解析失败（tool_call is None）** 的分支里将该文本视为“最终回复”，因此用户看到的是控制 JSON，而不是自然语言答案。

---

## 2. 思考过程：我如何定位问题（可审计）

### 2.1 先确认“控制协议”从哪来的
我先看系统提示词定义（`src/clude_code/orchestrator/agent_loop/prompts.py`），发现：
- `_BASE_SYSTEM_PROMPT` **全局**硬编码了：
  - “控制协议（step_done/replan）强制”
  - “任务输出结构（必须两段 + 必须输出工具 JSON）”

这意味着：即便是**简单对话/轻量 ReAct**，模型也会被强制要求输出控制 JSON 或工具 JSON。

### 2.2 再确认 ReAct 的“收口条件”
我再看 ReAct 回路（`src/clude_code/orchestrator/agent_loop/react.py`）：
- 只要 `_try_parse_tool_call(assistant)` 返回 `None`，就直接把 `assistant` 当最终回复返回。

结合 2.1：模型在强规则下输出了 `{"control":"step_done"}`（不是工具 JSON），解析器自然返回 `None`，于是被当最终回复。

### 2.3 额外放大器：过大的输出上限
日志里 `max_tokens` 仍为 **409600**。输出上限过大常见副作用：
- 模型更容易“复读/填充”
- 控制 JSON 这种短输出后容易继续生成，出现重复 JSON 的概率上升

---

## 3. 结论：这是“场景隔离缺失”导致的系统性问题

**本质矛盾**：
- `step_done/replan` 是“计划执行步骤”的控制信号；
- 但它被写进了“全局系统提示词”，导致 ReAct/闲聊也被迫输出控制信号；
- ReAct 的终止条件又把“非工具 JSON”当作可直接呈现给用户的最终答复。

---

## 4. 修复方案（已落地）

### 4.1 方案一：全局提示词“去强制化”（场景隔离）
**改动点**：`src/clude_code/orchestrator/agent_loop/prompts.py`
- 去掉“全局控制协议强制”与“强制两段输出结构”
- 改为更符合业界的规则：
  - 需要工具时：只输出工具 JSON
  - 不需要工具时：输出自然语言答案（不输出控制 JSON）
- 同时把工具清单的 schema 注入改为默认关闭，避免 system prompt 膨胀导致复读/挤压上下文。

### 4.2 方案二：ReAct 场景增加“控制 JSON 拦截护栏”
**改动点**：`src/clude_code/orchestrator/agent_loop/react.py`
- 当 `tool_call is None` 且 `assistant` 能解析为 `ControlEnvelope` 时：
  - 视为**无效最终回复**
  - 追加一条用户指令，要求改为自然语言回答
  - `continue` 进入下一轮（而不是直接返回给用户）

这属于业界常见的“输出后处理护栏”：避免协议内容泄露到用户界面。

### 4.3 方案三：修正输出上限默认值
**改动点**：`src/clude_code/config.py`
- 将 `LLMConfig.max_tokens` 默认值改为 `1024`
- 这能显著降低复读/超时/卡住概率，并与我们此前对 ReAct hang 的治理目标一致。

---

## 5. 额外修复：敏感信息默认值治理（顺手修正）

我在 `src/clude_code/config.py` 发现 `WeatherConfig.api_key` 存在硬编码默认值（属于严重安全问题）。
已改为默认空字符串，继续支持环境变量 `OPENWEATHERMAP_API_KEY` 注入。

---

## 6. 验收标准（如何判断修复成功）

输入：`获取今天北京的天气`

预期：
- 模型应输出工具调用 JSON `{"tool":"get_weather",...}` 或自然语言；
- **不再出现**把 `{"control":"step_done"}` 当最终回复输出给用户；
- 即便模型偶发输出控制 JSON，ReAct 护栏会拦截并要求它重新自然语言回答；
- `max_tokens` 日志应显示为 1024（或用户配置值）。


