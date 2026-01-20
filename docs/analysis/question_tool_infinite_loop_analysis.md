# `question` 工具死循环复盘与修复方案

> 目标：解释为什么会出现 `question -> display -> question -> ...` 直到 20 次熔断，并给出可落地修复。

---

## 1. 现象（基于你提供的日志）

你提供的 messages 片段显示，在一次“获取北京天气（但 API Key 未配置）”的流程中：
- 先触发 `get_weather` 返回 `E_CONFIG_MISSING`（合理）
- 随后 LLM 反复调用：
  - `question`：询问“希望如何配置 API Key”
  - `display`：重复输出同一段配置指引
  - 再次 `question`：询问“你选择哪种方式”
- 最终命中 ReAct 的硬熔断：**达到本轮最大工具调用次数（20）**

这是一种典型的“交互工具在无交互通道场景被回喂给模型导致的自激振荡”。

---

## 2. 思考过程：我如何定位根因（可审计）

### 2.1 先看 `question` 工具本身返回什么
文件：`src/clude_code/tooling/tools/question.py`

结论：`ask_question()` 当前只是一个“占位实现”，它永远返回：
- `ok=True`
- `payload.type="question"`
- `payload.status="pending"`

关键点：**它不会产生“用户答案”**。

### 2.2 再看 ReAct 循环如何处理工具结果
文件：`src/clude_code/orchestrator/agent_loop/react.py`

原逻辑：
- 工具执行后会把结果回喂给 LLM（`_tool_result_to_message`）
- 然后进入下一轮 LLM 调用

这会导致：模型看到了“status=pending（等待用户）”，但实际上系统并没有把用户的真实输入注入到同一个 turn 内，于是模型只能再次调用 `question` / `display` 来“努力完成任务”，从而死循环。

### 2.3 为什么会触发 20 次熔断
ReAct 回路本身有硬上限：
- `for iteration in range(20)`（避免无限循环）

所以它必然会在 20 次后停止，但用户体验是“突然停止 + 任务未完成”。

---

## 3. 根因总结（工程结论）

**根因**：`question` 工具当前没有“等待并接入用户回答”的运行时能力，却被允许在 ReAct 中无限调用；结果回喂给模型后，模型为了完成“拿到用户答案”的目标，会不断重复调用 `question`，形成自激循环。

这是典型的“工具契约不完整导致的控制闭环缺失”。

---

## 4. 修复方案（已落地）

### 4.1 业界做法（Claude Code / Cursor 思路）
当出现“需要用户回答”的交互节点时：
- 系统应当**暂停本轮 Agent 执行**
- 将问题直接呈现给用户
- 等待用户下一条输入作为回答
- 再继续后续步骤

### 4.2 本项目落地实现
文件：`src/clude_code/orchestrator/agent_loop/react.py`

改动：对 `question` 工具做特殊处理：
- 当 `tool == "question"` 且 `payload.status == "pending"`：
  - **不再把结果回喂给 LLM**
  - 直接把问题渲染成面向用户的自然语言（含选项列表）
  - 结束本轮 turn，等待用户下一次输入

这样可以保证：
- 不会继续进入下一轮 LLM 调用
- 不会出现 `question -> display` 循环
- 用户能在 CLI/TUI 中直接看到“请回复 1/2/3 …”

---

## 5. 验收标准

场景：未配置 OpenWeatherMap API Key 时，输入“获取北京的天气”

预期：
- 首先提示 API Key 未配置（来自 `get_weather` 的增强型错误回喂）
- 如模型选择调用 `question` 工具，则系统应输出一次“请回复选项序号或直接输入你的答案”
- **不应**触发 20 次工具调用熔断


