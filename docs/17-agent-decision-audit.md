# 17｜Agent 决策链路审计（业界对标）与模块级开发计划

> 目标：把 `AgentLoop` 的“决策链路”（意图分流 → 规划 → 执行 → 工具生命周期 → 重规划/降级 → 验证闭环）做一次可复盘的工程化审计，输出**问题清单（P0/P1/P2）+ 根因分析 + 模块到功能的开发计划 + 验收标准**。  
> 对标参考：Claude Code / Aider / Cursor（单入口、强契约、强可观测、可自愈、可回放）。

（正文内容将在后续段落补齐）

---

## 1. 范围与入口（What we are auditing）

### 1.1 关键入口
- **回合入口**：`src/clude_code/orchestrator/agent_loop/agent_loop.py::AgentLoop.run_turn`
- **规划**：`src/clude_code/orchestrator/agent_loop/planning.py::execute_planning_phase`
- **计划解析**：`src/clude_code/orchestrator/planner.py::parse_plan_from_text`
- **按步执行**：`src/clude_code/orchestrator/agent_loop/execution.py::execute_plan_steps`
- **工具生命周期**：`src/clude_code/orchestrator/agent_loop/tool_lifecycle.py::run_tool_lifecycle`
- **LLM 统一出口**：`src/clude_code/orchestrator/agent_loop/llm_io.py::llm_chat`
- **ReAct 降级**：`src/clude_code/orchestrator/agent_loop/react.py::execute_react_fallback_loop`

### 1.2 “决策”在这里指什么
本项目里，Agent 的“决策”不是单一函数，而是由一组“门 + 协议 + 状态机”共同决定：
- **门（Gate）**：是否启用显式 Plan（意图识别 → enable_planning）
- **协议（Protocol）**：LLM 输出必须是“工具调用 JSON”或“控制信号（STEP_DONE/REPLAN）”
- **状态机（State）**：INTAKE/PLANNING/EXECUTING/VERIFYING/DONE 等
- **闭环（Loop）**：工具结果回喂 → LLM 再决策 → 直到完成/失败/停止原因

---

## 2. 端到端决策链路（E2E Flow）

### 2.1 `run_turn`：本轮总控（single-turn orchestrator）
1) **构造 trace_id + 事件出口 `_ev`**：聚合 events，必要时写 trace/audit，并推送 live UI  
2) **意图识别**：`IntentClassifier.classify()` → 决定是否进入显式规划  
3) **构造 user_content**：把 planning_prompt 拼进同一条 user 消息（兼容 llama.cpp 的 role 交替要求）  
4) 若 **enable_planning=True**：
   - `execute_planning_phase()` 让 LLM 输出 Plan JSON
   - `parse_plan_from_text()` 解析并校验 Plan（含 step_id 唯一性）
   - 进入 `execute_plan_steps()` 执行
5) 若 **无 plan**：进入 `react.py` 的 ReAct fallback（工具循环）
6) **最终输出**：写 audit/trace + 更新 messages 历史

### 2.2 `execution`：计划执行（step-level loop）
每个步骤 step：
- 依赖检查：不满足则 `blocked`
- 进入最多 `max_step_tool_calls` 次迭代：
  - 注入 `step_prompt`（要求 display + 工具 JSON / STEP_DONE / REPLAN）
  - 调 LLM（`llm_io.llm_chat`）
  - 解析控制信号：
    - STEP_DONE → step.done
    - REPLAN → step.failed + 触发 `handle_replanning()`
  - 解析工具调用 JSON → `run_tool_lifecycle()` → 工具结果回喂
若 step 最终失败：触发重规划，或达到 `max_replans` 停止。

### 2.3 `tool_lifecycle`：工具执行闭环（policy + confirm + audit + verify）
对每次工具调用：
- 工具权限：`allowed_tools / disallowed_tools`
- 副作用确认：`write/exec` 按 policy 询问
- 安全评估：`exec` 先 `evaluate_command()`
- 核心执行：`dispatch_tool()`
- 审计落盘：`audit.jsonl`
- 选择性验证：对写/执行类工具成功后触发 `Verifier.run_verify(modified_paths=...)`

### 2.4 `llm_io`：请求/响应“统一出口”
核心职责：
- 规范化 messages（合并连续同 role，避免 llama.cpp 模板报错）
- 落盘请求参数（含 messages 摘要）与响应摘要（便于复盘）
- 发出事件：`llm_request_params`、`llm_response_data`、`llm_usage`

---

## 3. 业界对标：我们做对了什么（Strengths）

### 3.1 单一执行闭环
规划（Plan）与执行（Step）是一条可追踪主链路，且具备 stop_reason/重规划上限等“工程护栏”。

### 3.2 工具执行有“生命周期治理”
policy/confirm/audit/verify 的顺序清晰，且在工具层统一封装，避免每个调用点重复实现。

### 3.3 可观测性事件贯穿
`_ev` 将 turn 事件聚合，live UI/TUI 能消费同一协议，具备向 Claude Code 对齐的基础条件。

---

## 4. 发现的问题清单（含根因与风险）

> 标注方式：**P0**=会导致错误行为/体验断裂/可追溯性失真，必须优先；**P1**=复杂任务会放大，建议尽快；**P2**=中长期工程化演进。

### 4.1 P0：决策正确性与可追溯性风险

#### P0-A：trace_id 生成不稳定，影响“复盘/归因/bug 报告”
- **现状**：`trace_id = f"trace_{abs(hash((session_id, user_text)))}"`（依赖 Python `hash()`）  
- **问题**：
  - Python 的 `hash()` 跨进程默认随机化（hash seed），导致同样输入在不同进程 trace_id 不一致
  - 碰撞概率非零；同 session 同输入会复用同 trace_id（不利于多次尝试的区分）
- **风险**：`/bug`、trace 回放、UI 事件归因会变得不可靠
- **业界建议**：改为 `uuid4()` 或 `time_ns + counter`（保证唯一 + 可排序）
- **涉及模块**：Orchestrator / Observability / UI

#### P0-B：步骤完成/重规划依赖“字符串关键字”，协议易碎
- **现状**：通过包含 `STEP_DONE/REPLAN` 子串判断（且允许中文括号）  
- **问题**：
  - 关键字可能出现在解释文本/示例 JSON 中造成误判
  - 一旦模型输出风格变化（多余换行/格式化），会导致步骤永远无法收敛
- **风险**：执行循环发散；用户观感是“卡住/乱试工具/不结束”
- **业界建议**：
  - 使用结构化控制协议（例如 XML 标签 `<control action="step_done"/>` 或严格 JSON envelope）
  - 解析层做“强判定”：控制帧必须是**整段输出唯一内容**，否则视为普通文本
- **涉及模块**：Orchestrator（execution/parsing）/ Prompts

#### P0-C：重规划是“整计划重写”，信息丢失且成本高
- **现状**：`handle_replanning()` 让 LLM 输出新的完整 Plan，`step_cursor=0` 从头开始  
- **问题**：
  - 已完成步骤的“证据”与“关键结论”可能在上下文裁剪中丢失
  - 重规划成本随 steps 数增长；且容易引入新依赖/新步骤导致振荡
- **风险**：token 激增、执行不收敛、重复劳动
- **业界建议**：局部重规划（Plan patch）：只替换失败 step 或追加修复 steps，并保留 done steps 的摘要
- **涉及模块**：Orchestrator（planning/execution）/ Context

### 4.2 P1：健壮性与一致性风险

#### P1-A：复读/异常输出检测过于粗糙（误伤/漏判）
- **现状**：`assistant.count("[") > 50 or assistant.count("{") > 50` 视为复读  
- **问题**：长 JSON / 代码片段会误判；真正的低熵复读不一定触发该阈值  
- **业界建议**：使用 n-gram 重复率或熵值检测；并区分“结构化输出很长”和“无意义复读”

#### P1-B：Plan JSON 解析策略偏脆（多候选提取=启发式）
- **现状**：`_extract_json_candidates()` 通过 fenced code block/首尾大括号截取  
- **风险**：模型输出含多个 JSON/含解释文字时，容易截到错误片段  
- **业界建议**：引入严格 JSON envelope 或改用更稳的 JSON 提取（例如：寻找最外层合法 JSON 的流式扫描）

#### P1-C：事件协议命名/粒度不一致的潜在风险
- **现状**：同一语义在不同路径可能产生不同事件名（例如 `llm_response` vs `llm_response_data`）  
- **风险**：不同 UI 消费方需要写大量兼容逻辑；一旦遗漏就出现“有的窗格没数据”  
- **业界建议**：定义稳定的 EventSpec（字段、必填、版本号），在 `_ev` 统一归一化/补字段

#### P1-D：异常吞掉仍存在（影响排障）
- **现状**：少量 `except Exception: pass` 仍存在（例如：用量记录/非关键事件上报）  
- **风险**：关键链路隐性失败却无日志  
- **业界建议**：至少写 file-only warning + trace_id，保持“用户不刷屏、排障可追踪”

### 4.3 P2：工程化演进方向（业界成熟形态）

#### P2-A：缺少“工作记忆（Working Memory）”与“阶段摘要（Milestone Summary）”
- **现状**：依赖 messages 历史 + `_trim_history()` 的裁剪策略  
- **风险**：复杂任务中，关键发现（入口文件/关键符号/约束）被裁剪后，模型后续决策退化
- **业界建议**：
  - 引入 `WorkingMemory`：结构化存储（入口文件、关键符号、已验证结论、待办）并固定注入
  - 每步完成产出“摘要条目”进入工作记忆，而不是把全部 tool 输出留在对话里

---

## 5. 完整结论（Executive Summary）

### 5.1 一句话结论
当前 Agent 决策链路已经具备“规划-执行-工具闭环”的骨架，但在**可追溯标识、控制协议稳定性、重规划成本与信息保真**上存在业界 P0 级缺口；若不先收敛这些基础设施问题，后续再堆 UI/功能会被“偶发卡死/不收敛/难复盘”反复拖累。

### 5.2 最重要的 4 个结论
- **结论 1（可追溯性）**：trace_id 必须稳定且唯一，否则所有观测/bug 报告/归因都会失真（P0）。
- **结论 2（控制协议）**：STEP_DONE/REPLAN 这类“关键字协议”会在模型波动时崩掉，必须升级为结构化控制帧（P0）。
- **结论 3（重规划）**：整计划重写导致高成本与振荡，应引入局部重规划与工作记忆（P0→P1）。
- **结论 4（工程化演进）**：下一阶段的“业界级”不是再加工具，而是把决策链路做成**可验证、可回放、可降级**的产品级闭环（P1/P2）。

---

## 6. 模块到功能的开发计划（含验收标准）

> 说明：这里给出“模块 → 功能点 → 关键改动 → 验收标准”的完整落地清单，可直接转为 issue/里程碑。

### 6.1 P0（必须先做：保证正确性与一致性）

#### P0-1 Orchestrator：trace_id 改为稳定唯一
- **改动点**：`AgentLoop.run_turn` 生成 trace_id 的方式
- **方案**：
  - `uuid4()`（简单可靠）或 `time_ns + 自增 counter`（有序）
  - trace_id 贯穿 `_ev`、audit、UI、`/bug` 产物
- **验收标准**：
  - 同一 session 同一输入重复执行，trace_id 必不同
  - 同一输入跨进程执行，trace_id 仍合法且不依赖 Python hash seed

#### P0-2 Orchestrator：升级“步骤控制协议”
- **改动点**：`execution.execute_single_step_iteration` 的输出解析
- **方案**（二选一，推荐 A）：
  - A) **控制帧 JSON**：`{"control":"step_done"}` / `{"control":"replan"}`（整段输出唯一内容）
  - B) XML 控制帧：`<control action="step_done"/>`
- **验收标准**：
  - 任意包含 STEP_DONE 字样的普通解释文本不再误触发
  - 当模型输出不符合协议时，系统能给出“纠错提示 + 自动重试（有限次数）”

#### P0-3 Orchestrator：局部重规划（Plan patch）
- **改动点**：`handle_replanning` 不再要求整 Plan 重写
- **方案**：
  - 输入：失败 step_id + 最近关键工具反馈摘要 + 工作记忆
  - 输出：`patch`（替换该 step 描述/依赖或插入 1~N 个新 steps）
  - 保留已完成 steps 为 done，并固定注入其摘要（防止遗忘）
- **验收标准**：
  - 重规划 token/耗时相较整 Plan 明显下降（至少 30%）
  - 不会频繁“推倒重来”，且能收敛到完成或清晰 stop_reason

### 6.2 P1（健壮性：复杂任务不崩）

#### P1-1 Planner：Plan 提取与解析加固
- **改动点**：`planner._extract_json_candidates` / `parse_plan_from_text`
- **方案**：
  - 引入严格 envelope（要求输出第一段为 JSON，不允许夹杂）
  - 或实现“最外层合法 JSON”扫描提取（减少误截断）
- **验收标准**：
  - 常见非标输出（fence、解释文本）下仍能高成功率解析
  - 解析失败可给出清晰错误原因（JSON decode / schema validate / unique id）

#### P1-2 Execution：复读检测升级
- **改动点**：复读/异常输出检测
- **方案**：n-gram 重复率或熵检测；并对“长 JSON/长代码”免疫
- **验收标准**：误伤率显著下降；卡死率下降；触发时能给出清晰 stop_reason 与纠错提示

#### P1-3 EventSpec：事件协议版本化与归一化
- **改动点**：在 `_ev` 统一补齐字段/命名，定义 EventSpec 文档
- **验收标准**：classic/enhanced/opencode 三种 UI 均能稳定显示关键窗格数据，不需要 UI 写兼容分支

### 6.3 P2（产品化：可回放、可解释、可迭代）

#### P2-1 WorkingMemory：工作记忆与阶段摘要
- **改动点**：Orchestrator 新增 `WorkingMemory` 数据结构与注入点
- **验收标准**：复杂任务中“入口文件/关键符号/约束”不会因裁剪丢失；重规划成功率提升

#### P2-2 Replay：trace/audit 回放工具
- **改动点**：Observability 增加 `clude replay <trace_id>` 或 `--replay` 模式
- **验收标准**：能复现一轮 turn 的关键事件序列（LLM params 摘要、工具调用、结果、stop_reason）




