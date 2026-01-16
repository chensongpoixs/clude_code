# 02｜工具协议（Tool/Function Calling）与权限/沙箱（可实现规格）

本章定义“代理如何调用工具”，目标是：**一致、可校验、可审计、可扩展**。

## 1. 工具总原则

- 工具是“受控能力边界”，代理不得直接做文件 IO/执行命令，必须通过工具层。
- 每个工具都声明：
  - **name**
  - **version**
  - **description**
  - **args_schema**（JSON Schema 或等价结构）
  - **return_schema**
  - **required_permissions**（read/write/exec/network 等）
  - **side_effects**（是否写文件、是否创建进程等）

## 2. 工具调用消息格式（建议）

### 2.1 ToolCallRequest
- `tool_call_id: string`（全局唯一，便于回放）
- `name: string`
- `version: string`
- `args: object`
- `requested_permissions: string[]`（可选：更细粒度）
- `trace_id: string`
- `timestamp: number`

### 2.2 ToolCallResult
统一返回结构，避免“成功/失败”在不同工具里不一致：
- `tool_call_id: string`
- `ok: boolean`
- `payload: object | null`（成功结果）
- `error: { code: string, message: string, details?: object } | null`
- `artifacts?: { files_changed?: string[], commands_run?: string[] }`
- `duration_ms: number`

## 3. 参数校验与类型系统

### 3.1 Schema 校验
- 工具层必须对 `args` 做严格校验（缺字段/多字段/类型不符都拒绝）
- 建议支持：
  - `additionalProperties: false`（防止偷偷塞参数）
  - 对路径参数进行规范化（normalize）后再做策略校验

### 3.2 统一路径语义
- 所有路径都必须显式声明：
  - 相对 workspace 的相对路径（优先）
  - 绝对路径（默认禁用，需策略放行）
- 工具层最终执行前必须做：
  - `realpath`/符号链接解析
  - 路径是否在 workspace 内

## 4. 权限模型（Policy）

### 4.1 权限类型（示例）
- `fs.read`
- `fs.write`
- `fs.delete`
- `proc.exec`
- `net.connect`
- `git.write`（commit/push）

### 4.2 策略评估（Policy Engine）

建议将策略评估做成纯函数：
- 输入：`ToolCallRequest` + `WorkspaceContext` + `UserConfig`
- 输出：`ALLOW | DENY(code, reason) | REQUIRE_CONFIRMATION(scope)`

#### 4.2.1 典型规则
- **路径边界**：禁止访问 workspace 外路径；禁止访问 `.ssh/`、系统凭据目录等
- **命令 allowlist/denylist**：允许 `npm test`，禁止 `rm -rf /`、`powershell Invoke-WebRequest`（默认网络禁用）
- **网络**：默认 `DENY`，企业版基于域名/IP allowlist
- **写操作**：默认允许但需要“变更预览/可撤销”；高风险（删除/批量改）走确认

## 5. 沙箱（Sandbox）与执行隔离

### 5.1 文件系统沙箱
- 工具层强制将所有相对路径解析到 workspace
- 对 `..`、符号链接穿透做防护（realpath 再判断前缀）
- 写入时用“原子写”：
  - 写临时文件 → fsync → rename 覆盖

### 5.2 进程执行沙箱
- 设置工作目录为 workspace
- 继承最小环境变量（过滤 `*_TOKEN` 等敏感变量）
- 超时与输出上限：
  - `timeout_ms`（默认 2~5 分钟）
  - `max_output_bytes`（默认 1~5MB，超出裁剪并保留尾部）
- 后台任务：
  - 必须记录 `pid` 与启动参数
  - 提供查询/停止工具（可选）

## 6. 工具清单（MVP 推荐）

### 6.1 文件类
- `list_dir(path, ignore_globs?)`
- `glob_file_search(glob_pattern, target_directory?)`
- `read_file(path, offset?, limit?)`
- `apply_patch(patch_text)`：统一的补丁入口（推荐）
- `delete_file(path)`

### 6.2 搜索类
- `grep(pattern, path?, glob?, multiline?, head_limit?, -i?)`
- `codebase_search(query, target_directories[])`（语义检索，可选/可降级）

### 6.3 执行类
- `run_terminal_cmd(command, is_background)`（受策略保护）

### 6.4 输出/交互类（MVP 推荐）

#### 6.4.1 `display`（业界对标：Claude Code 的 `message_user`）

用途：让 Agent 在执行长任务时**主动向用户输出进度/中间结论/说明**，而不是只能等到最终 `final_text` 才看到结果。

- **安全性**：不读写文件、不执行命令，仅输出信息；因此在策略层通常不需要用户确认。
- **工程价值**：显著降低“黑盒执行感”，提升可观测性与可控性（尤其在 `--live` 模式下）。

**args_schema（JSON Schema）**：

```json
{
  "type": "object",
  "properties": {
    "content": { "type": "string", "description": "要显示给用户的内容（支持 Markdown）" },
    "level": {
      "type": "string",
      "enum": ["info", "success", "warning", "error", "progress"],
      "default": "info",
      "description": "消息级别（影响显示样式）"
    },
    "title": { "type": "string", "description": "可选标题（用于分段显示）" }
  },
  "required": ["content"],
  "additionalProperties": false
}
```

**示例**：

```json
{"tool":"display","args":{"content":"正在分析第 3/10 个文件…","level":"progress"}}
```

```json
{"tool":"display","args":{"title":"代码审计","content":"发现 2 处高风险点，准备修复。","level":"warning"}}
```

```json
{
  "tool": "display",
  "args": {
    "title": "执行思路",
    "level": "info",
    "content": "准备收敛入口：先统一事件协议，再迁移 UI 到 plugins。",
    "thought": "原因：目前存在多入口导致行为分裂；先把链路收口才能保证 UI/工具/审计一致。",
    "evidence": ["入口: cli/chat_handler.py", "UI: plugins/ui/opencode_tui.py", "协议: docs/02-tool-protocol.md"]
  }
}
```

**实现说明（本项目）**：
- 分发：`src/clude_code/orchestrator/agent_loop/tool_dispatch.py`（ToolSpec 注册 + handler）
- 执行：`src/clude_code/tooling/tools/display.py`（事件广播 + 控制台降级 + 审计）
- UI：`src/clude_code/cli/live_view.py`（监听 `display` 事件并渲染到“思考滑动窗口”）

**为什么你可能“看不到 display 输出”？（常见误区）**：
- `display` 是一个工具：只有模型**实际调用**它（或编排器主动触发）才会出现输出。
- 本项目已在系统提示词与步骤提示中加入“过程可见性”约束（鼓励多步骤任务在步骤开始时先 `display` 一次）。
- 若你使用 `--live`：`display` 会进入实时面板的“思考输出滑动窗口”。  
  若不使用 `--live`：`display` 会降级为 `loop.logger.info(...)` 输出一条预览。

### 6.4 质量类
- `read_lints(paths[])`（与 IDE/LSP 或内置 linter 对接）

### 6.5 记忆类（可选）
- `update_memory(action, title, knowledge_to_store, existing_knowledge_id)`

## 7. 审计日志（必做）

每次工具调用必须写一条结构化日志（JSON Lines 推荐）：
- `trace_id`、`tool_call_id`
- `name/version`
- `args`（敏感字段脱敏）
- `result.ok`
- `error.code`
- `duration_ms`
- `artifacts.files_changed / commands_run`

## 8. 工具版本与兼容

### 8.1 版本策略
- `MAJOR`：破坏性变更（schema/语义改变）
- `MINOR`：新增可选字段或新工具
- `PATCH`：修 bug，不改 schema

### 8.2 向后兼容要求
- 工具层必须能识别“旧 schema”的请求并给出明确错误提示或自动适配


