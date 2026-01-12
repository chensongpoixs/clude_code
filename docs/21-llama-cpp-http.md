# 21｜LLM 接入：llama.cpp HTTP API（Day1 可跑）

本章给出“Python 纯 CLI”对接 `llama.cpp server` 的最小可用方式：启动、连通性、常见坑、以及 clude 的配置项。

## 1. 启动 llama.cpp server（示例）

> 以你实际的 llama.cpp 构建方式为准；这里只描述“需要暴露 HTTP API”这一点。

### 1.1 OpenAI 兼容模式（推荐）

目标：提供 `POST /v1/chat/completions`。

检查点：
- 访问 `http://127.0.0.1:8080/v1/models`（若支持）
- 或直接用 `POST /v1/chat/completions` 发一个最小请求（见 2.1）

### 1.2 Completion 模式（备用）

目标：提供 `POST /completion`（返回 `{"content": "..."}`）。

当你的 server 不支持 OpenAI 兼容接口时，将 clude 的 `api_mode` 设为 `completion`。

## 2. 连通性自检

### 2.1 OpenAI 兼容接口最小请求

请求：
- url：`{base_url}/v1/chat/completions`
- body（JSON）：
  - `messages`: `[{role, content}...]`
  - `temperature`, `max_tokens`, `stream=false`

成功响应必须包含：
- `choices[0].message.content`

### 2.2 Completion 接口最小请求

请求：
- url：`{base_url}/completion`
- body：`{prompt, temperature, n_predict}`

成功响应建议包含字段：
- `content`（clude 会优先读取）

## 3. clude 侧配置（当前实现）

### 3.1 环境变量

使用 `pydantic-settings`，前缀为 `CLUDE_`。

- `CLUDE_WORKSPACE_ROOT`：workspace 根目录（默认 `.`）
- `CLUDE_LLM__BASE_URL`：llama.cpp base_url（默认 `http://127.0.0.1:8080`）
- `CLUDE_LLM__API_MODE`：`openai_compat` 或 `completion`
- `CLUDE_LLM__TEMPERATURE`：默认 `0.2`
- `CLUDE_LLM__MAX_TOKENS`：默认 `1024`
- `CLUDE_LLM__TIMEOUT_S`：默认 `120`

### 3.2 策略（确认）
- `CLUDE_POLICY__CONFIRM_WRITE`：写文件是否需要确认（默认 true）
- `CLUDE_POLICY__CONFIRM_EXEC`：执行命令是否需要确认（默认 true）

## 4. 运行 clude（Day1）

安装（开发模式）：
- `pip install -e .`

启动：
- `clude chat`
 - 选择模型（openai_compat）：
   - `clude models`
   - `clude chat --select-model`
   - 或 `clude chat --model <model_id>`

交互说明：
- 你输入任务；模型会输出中文说明或输出一个 JSON 工具调用：
  - `{"tool":"read_file","args":{"path":"README.md"}}`
- clude 执行工具并将结果回喂模型，形成最小“读/搜/写/跑命令”闭环。

## 5. 常见问题

### 5.0 返回 400 Bad Request（你遇到的情况）

`400` 的关键信息通常在 **response body** 里（llama.cpp 会说明哪个字段不对）。

从 v0.1.0 起 clude 会把 400 的 body 打出来（截断 2000 字符），排查流程建议：
- 先跑 `clude doctor`，看：
  - `api_mode` 是否正确（openai_compat vs completion）
  - `/v1/models first_id` 是否能取到
- 若 openai_compat：
  - **最常见原因**：请求里的 `model` 不在 `/v1/models` 列表里 → 直接 400
  - 解决：设置 `CLUDE_LLM__MODEL` 为 `doctor` 输出的 `first_id`
- 若 body 提示字段名不匹配：
  - 切换 `completion` 模式：`CLUDE_LLM__API_MODE=completion`

### 5.1 模型不按 JSON 工具协议输出
- 降低 temperature（如 0.1~0.3）
- 换 chat template 更“指令跟随”的模型
- 在系统提示里更强约束（后续可以加“违规即重试”的守卫逻辑）

### 5.2 404 /v1/chat/completions
- 将 `CLUDE_LLM__API_MODE=completion`
- 或确认 llama.cpp server 是否启用了 OpenAI 兼容路由


