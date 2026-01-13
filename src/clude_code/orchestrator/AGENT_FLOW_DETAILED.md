# Agent 完整执行流程详细说明

## 概述

本项目实现了基于 **ReAct (Reasoning + Acting)** 模式的 Code Agent，通过 LLM 与工具调用的循环交互，完成代码分析、修改、执行等任务。

## 一、初始化阶段（AgentLoop.__init__）

### 1.1 核心组件初始化

```
1. 创建 LLM 客户端（LlamaCppHttpClient）
   - base_url: llama.cpp HTTP 服务器地址
   - api_mode: openai_compat 或 completion
   - model: 模型 ID
   - temperature, max_tokens, timeout_s

2. 初始化工具集（LocalTools）
   - workspace_root: 工作区根目录
   - max_file_read_bytes: 文件读取限制
   - max_output_bytes: 输出限制

3. 初始化审计和追踪日志
   - AuditLogger: 记录关键操作（JSONL 格式）
   - TraceLogger: 记录详细执行轨迹（JSONL 格式）

4. 启动知识/RAG 系统
   - IndexerService: 后台异步索引服务（LanceDB）
   - CodeEmbedder: 代码嵌入向量生成
   - VectorStore: 向量存储和搜索
```

### 1.2 系统提示词构建

```
1. 生成 Repo Map（使用 ctags）
   - 提取代码仓库的符号（函数、类、变量）
   - 提供全局代码结构概览

2. 收集环境信息
   - 操作系统类型和版本
   - 工作区绝对路径

3. 组合系统提示词
   - 核心元规则（身份锚定、语言锁死、严禁推诿）
   - 任务输出架构（思路分析 + 工具调用）
   - 环境信息和 Repo Map
```

### 1.3 消息历史初始化

```
messages = [
    ChatMessage(role="system", content=combined_system_prompt)
]
```

## 二、用户输入处理（run_turn 开始）

### 2.1 意图识别与决策门（Phase 4 新增）

```
1. 意图分类（Intent Classification）
   - 使用 IntentClassifier（LLM 驱动 + 启发式）对输入进行语义分类。
   - 标签包括：CODING_TASK, CAPABILITY_QUERY, REPO_ANALYSIS, GENERAL_CHAT, UNCERTAIN。
   - 目的：在进入复杂规划前，识别用户真实意图。

2. 决策门（Decision Gate）
   - 根据意图结果动态调整策略：
     - 若为 CAPABILITY_QUERY (能力询问) 或 GENERAL_CHAT (通用对话)：
       - 强制将 enable_planning 设为 False。
       - 跳过显式规划阶段，直接进入单层对话或简易工具探测。
     - 若为 CODING_TASK (代码任务)：
       - 保持 enable_planning=True（如果配置开启）。
       - 准备进入 Phase 3 的“显式规划”流程。

3. 记录事件
   - intent_classified: 记录分类结果、理由和置信度。
```

### 2.2 输入预处理（原有流程）

```
1. 记录用户消息到审计日志
   audit.write(trace_id, "user_message", {text: user_text})

2. 添加到消息历史
   messages.append(ChatMessage(role="user", content=user_text))

3. 裁剪历史（保持上下文窗口）
   _trim_history(max_messages=30)
```

## 三、ReAct 循环（最多 20 次迭代）

### 3.1 LLM 请求阶段

```
步骤 1: 记录请求参数（仅文件日志）
  - model, temperature, max_tokens
  - api_mode, base_url
  - messages_count
  - messages 预览（每条消息的前 200 字符）

步骤 2: 调用 LLM
  assistant = llm.chat(messages)

步骤 3: 异常检测
  - 检测复读字符（[ 或 { 超过 50 次）
  - 如果异常，截断并返回错误消息
```

### 3.2 响应解析阶段

```
步骤 1: 记录响应数据（仅文件日志）
  - text_length: 响应文本长度
  - text_preview: 前 500 字符预览
  - truncated: 是否截断
  - has_tool_call: 是否包含工具调用
  - tool_call: 工具调用 JSON（如果有）

步骤 2: 解析工具调用
  tool_call = _try_parse_tool_call(assistant)
  
  解析策略（多层容错）：
  a. 纯 JSON 对象：{...}
  b. 代码块包裹：```json {...} ```
  c. 最佳努力：提取第一个 {...} 对象
```

### 3.3 无工具调用分支（最终回复）

```
如果 tool_call is None:
  1. 保存完整 assistant 消息到历史
  2. 记录到审计日志
  3. 裁剪历史
  4. 返回 AgentTurn（包含最终文本）
```

### 3.4 工具调用分支

#### 3.4.1 工具调用记录

```
1. 提取工具名称和参数
   name = tool_call["tool"]
   args = tool_call["args"]

2. 清理 assistant 消息（只保留 JSON）
   clean_assistant = json.dumps(tool_call)
   messages.append(ChatMessage(role="assistant", content=clean_assistant))

3. 裁剪历史
```

#### 3.4.2 策略检查 - 用户确认

```
写文件操作确认（write_file, apply_patch, undo_patch）:
  if confirm_write:
    decision = confirm("确认写文件？")
    if not decision:
      - 记录拒绝消息
      - 回喂错误结果给 LLM
      - continue（跳过工具执行）

执行命令确认（run_cmd）:
  if confirm_exec:
    decision = confirm("确认执行命令？")
    if not decision:
      - 记录拒绝消息
      - 回喂错误结果给 LLM
      - continue（跳过工具执行）
```

#### 3.4.3 策略检查 - 命令黑名单

```
if name == "run_cmd":
  cmd = args["command"]
  dec = evaluate_command(cmd, allow_network)
  
  if not dec.ok:
    - 记录策略拒绝
    - 回喂错误结果给 LLM
    - continue（跳过工具执行）
```

#### 3.4.4 工具执行

```
1. 分发工具调用
   result = _dispatch_tool(name, args)
   
   支持的工具：
   - list_dir: 列出目录
   - read_file: 读取文件
   - glob_file_search: 文件搜索
   - grep: 文本搜索（优先 ripgrep）
   - apply_patch: 应用补丁
   - undo_patch: 回滚补丁
   - write_file: 写入文件
   - run_cmd: 执行命令
   - search_semantic: 语义搜索（向量 RAG）

2. 记录执行结果
   - 成功/失败状态
   - 错误信息（如果有）
   - payload（工具返回数据）
```

#### 3.4.5 结果回喂

```
1. 结构化反馈转换
   msg = _tool_result_to_message(name, result, keywords)
   
   转换策略：
   - 保留决策关键字段
   - 语义窗口采样（基于关键词）
   - 避免完整 payload 回喂

2. 添加到消息历史
   messages.append(ChatMessage(role="user", content=msg))

3. 裁剪历史
   _trim_history(max_messages=30)

4. 记录审计日志
   audit.write(trace_id, "tool_call", {...})
```

### 3.5 循环控制

```
- 最多执行 20 次迭代（防止死循环）
- 每次迭代后检查是否达到最大次数
- 如果达到，返回停止消息
```

## 四、历史裁剪机制（_trim_history）

### 4.1 裁剪策略

```
1. 检查消息数量
   if len(messages) <= max_messages:
     return  # 无需裁剪

2. 保留 system 消息
   system = messages[0]

3. 从尾部向前查找
   tail_start_idx = len(messages) - (max_messages - 1)
   
4. 确保第一条消息是 'user' 角色
   while messages[tail_start_idx].role != "user":
     tail_start_idx += 1

5. 重新组合消息
   messages = [system, *messages[tail_start_idx:]]
```

### 4.2 裁剪原因

```
- llama.cpp 等严格 chat template 要求 user/assistant 交替
- 控制上下文窗口大小（减少 Token 消耗）
- 保持最近的对话上下文
```

## 五、工具分发机制（_dispatch_tool）

### 5.1 工具路由

```
根据工具名称分发到对应执行函数：
  - list_dir → tools.list_dir()
  - read_file → tools.read_file()
  - grep → tools.grep()（优先 ripgrep）
  - apply_patch → tools.apply_patch()
  - search_semantic → _semantic_search()
  - ...
```

### 5.2 异常处理

```
try:
  return tool_execution()
except KeyError:
  return ToolResult(False, error="E_INVALID_ARGS")
except Exception:
  return ToolResult(False, error="E_TOOL")
```

## 六、语义搜索（_semantic_search）

### 6.1 搜索流程

```
1. 查询向量化
   q_vector = embedder.embed_query(query)

2. 向量搜索
   hits = vector_store.search(q_vector, limit=5)

3. 格式化结果
   payload_hits = [
     {path, start_line, end_line, text}
     for h in hits
   ]

4. 返回 ToolResult
```

## 七、返回结果（AgentTurn）

### 7.1 结果结构

```python
@dataclass
class AgentTurn:
    assistant_text: str      # 最终回复文本
    tool_used: bool          # 是否使用了工具
    trace_id: str           # 追踪 ID
    events: list[dict]      # 事件列表
```

### 7.2 事件列表

```
events 包含所有关键步骤：
  - user_message
  - llm_request
  - llm_response
  - tool_call_parsed
  - confirm_write/confirm_exec
  - policy_deny_cmd
  - tool_result
  - tool_result_fed_back
  - final_text
  - stop_reason
```

## 八、日志记录

### 8.1 日志类型

```
1. 控制台日志（可选）
   - 使用 Rich 格式化
   - 支持颜色和样式
   - 简洁格式（只显示消息内容）

2. 文件日志（始终启用）
   - 完整格式：级别 [文件名:行号] 级别 - 消息
   - 记录所有关键步骤
   - 包含 LLM 请求/响应详情

3. 审计日志（audit.jsonl）
   - 记录关键操作
   - 包含 trace_id 关联

4. 追踪日志（trace.jsonl）
   - 详细执行轨迹
   - 用于问题复现
```

## 九、关键设计决策

### 9.1 ReAct 模式

```
- 思考（Reasoning）：LLM 分析任务并决定工具调用
- 行动（Acting）：执行工具并获取结果
- 观察（Observing）：将结果回喂给 LLM
- 循环：重复直到任务完成或达到限制
```

### 9.2 上下文管理

```
- 历史裁剪：保持最近 30 条消息
- 结构化反馈：只回喂关键信息
- 语义窗口：基于关键词采样代码片段
```

### 9.3 安全性

```
- 用户确认：写文件/执行命令前确认
- 命令黑名单：禁止危险命令
- 工作区限制：只能访问工作区内的文件
- 环境变量清理：防止敏感信息泄露
```

### 9.4 健壮性

```
- 复读检测：防止模型输出异常
- 工具调用解析容错：多层解析策略
- 异常捕获：工具执行失败不影响主循环
- 最大迭代限制：防止死循环
```

## 十、流程图说明

详细的动画流程图请参考：![`agent_complete_flow_animated.svg`](/src/assets/agent_complete_flow_animated.svg)

流程图展示了从用户输入到最终回复的完整执行路径，包括：
- 初始化阶段
- ReAct 循环的每个步骤
- 决策分支（工具调用 vs 最终回复）
- 策略检查流程
- 工具执行和结果回喂
- 历史裁剪机制

