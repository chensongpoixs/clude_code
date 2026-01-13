import json
import re
from dataclasses import dataclass
from typing import Any, Callable, List, Dict, Optional

from clude_code.config import CludeConfig
from clude_code.llm.llama_cpp_http import ChatMessage, LlamaCppHttpClient
from clude_code.observability.audit import AuditLogger
from clude_code.observability.trace import TraceLogger
from clude_code.observability.logger import get_logger
from clude_code.policy.command_policy import evaluate_command
from clude_code.tooling.feedback import format_feedback_message
from clude_code.tooling.local_tools import LocalTools, ToolResult
from clude_code.knowledge.indexer_service import IndexerService
from clude_code.knowledge.embedder import CodeEmbedder
from clude_code.knowledge.vector_store import VectorStore


SYSTEM_PROMPT = """\
# 核心元规则 (META-RULES) - 优先级最高
1. **身份锚定**：你是一个名为 clude-code 的【开发架构师】。你不是对话助手，严禁表现得像个开发架构师。
2. **语言锁死**：必须 100% 使用【中文】与用户交流。严禁在【逻辑推演】和回复中使用英文单词（代码名、文件名除外）。
3. **严禁推诿/反问**：你有权限读取文件、执行命令。绝对禁止说“我无法访问”、“我只是一个语言模型”、“请提供更多信息”。如果你不确定，请立即调用工具自行探测。
4. **任务执行导向**：面对复杂指令（如分析、评分、重构），严禁在未获得充足数据前给出结论。第一步必须是调用探测工具（list_dir, read_file, glob_file_search 等）。

# 任务输出架构 (必须严格遵守)
每一步输出必须包含以下两个部分：
1. **思路分析**：
   - 【当前任务】：你正在处理用户指令的哪个具体子环节。
   - 【逻辑推演】：基于当前已获取的数据，你推导出的结论或下一步行动的理由。严禁复读 System Prompt。
   - 【下一步动作】：你将调用的工具及其必要性。
2. **工具调用**：必须输出且仅输出一个纯 JSON 对象。
   {"tool":"<name>","args":{...}}

# 评分与分析准则
- 当涉及“评分”时，必须对比 `src/INDUSTRY_CODE_AGENT_TECH_WHITEPAPER.md` 中的业界标准（如 Aider, Cursor, Claude Code）。
- 分析必须深入逻辑流、边界条件和跨文件依赖，严禁只列出函数名或文件名。

# 可用工具清单
  - list_dir: {"path":"."}
  - read_file: {"path":"...","offset":1,"limit":200}
  - glob_file_search: {"glob_pattern":"**/*.*"}
  - grep: {"pattern":"...","path":"."}
  - apply_patch: {"path":"...","old":"...","new":"..."}
  - search_semantic: {"query":"..."}
  - run_cmd: {"command":"..."}
"""


@dataclass
class AgentTurn:
    """
    Agent 一轮对话的返回结果。
    
    属性:
        assistant_text: Agent 的最终回复文本（如果未调用工具，则为完整回复；否则为最后一轮的工具调用结果）
        tool_used: 本轮是否使用了工具
        trace_id: 本轮对话的唯一追踪ID（用于日志关联）
        events: 本轮所有事件的列表（用于调试和可观测性）
    """
    assistant_text: str
    tool_used: bool
    trace_id: str
    events: list[dict[str, Any]]


def _try_parse_tool_call(text: str) -> dict[str, Any] | None:
    """
    从 LLM 的文本输出中尝试解析工具调用 JSON。
    
    本函数采用多层容错策略，支持以下格式：
    1. 纯 JSON 对象：直接以 `{` 开头、`}` 结尾的文本
    2. 代码块包裹：```json ... ``` 或 ``` ... ``` 中的 JSON
    3. 最佳努力：从文本中提取第一个 `{...}` 对象
    
    参数:
        text: LLM 的原始输出文本（可能包含解释性文字 + JSON）
    
    返回:
        解析成功的工具调用字典（包含 "tool" 和 "args" 键），失败返回 None
    
    流程图: 见 `agent_loop_parse_tool_call_flow.svg`
    """
    text = text.strip()
    # Allow the model to include explanations; try to extract JSON object from:
    # 1) raw text that is a JSON object
    # 2) fenced ```json ... ``` block
    # 3) first {...} object in the text (best-effort)
    candidates: list[str] = []
    if text.startswith("{") and text.endswith("}"):
        candidates.append(text)
    if "```" in text:
        for fence in ("```json", "```JSON", "```"):
            if fence in text:
                parts = text.split(fence, 1)
                if len(parts) == 2:
                    body = parts[1]
                    body = body.split("```", 1)[0]
                    body = body.strip()
                    if body.startswith("{") and body.endswith("}"):
                        candidates.append(body)
    # best-effort: find first JSON-ish object
    if "{" in text and "}" in text:
        start = text.find("{")
        end = text.rfind("}")
        if 0 <= start < end:
            candidates.append(text[start : end + 1].strip())

    obj = None
    for c in candidates:
        try:
            parsed = json.loads(c)
            if isinstance(parsed, dict):
                obj = parsed
                break
        except json.JSONDecodeError:
            continue
    if obj is None:
        return None
    if not isinstance(obj, dict):
        return None
    if "tool" not in obj or "args" not in obj:
        return None
    if not isinstance(obj["tool"], str) or not isinstance(obj["args"], dict):
        return None
    return obj


def _tool_result_to_message(name: str, tr: ToolResult, keywords: set[str] | None = None) -> str:
    """
    将工具执行结果转换为发送给 LLM 的结构化消息。
    
    本函数采用业界最佳实践：只保留决策关键字段和引用，避免将完整 payload 回喂给模型，
    从而减少 Token 消耗并提升模型聚焦度。
    
    参数:
        name: 工具名称（如 "read_file", "grep"）
        tr: 工具执行结果（ToolResult 对象）
        keywords: 可选的关键词集合，用于语义窗口采样（优先保留包含关键词的代码片段）
    
    返回:
        格式化的字符串消息，将被作为 "user" 角色的消息发送给 LLM
    
    流程图: 见 `agent_loop_tool_result_to_message_flow.svg`
    """
    # Centralized structured feedback (industry-grade stability):
    # keep decision-critical fields + references, avoid dumping full payload.
    return format_feedback_message(name, tr, keywords=keywords)


class AgentLoop:
    """
    Agent 核心循环类，实现 ReAct (Reasoning + Acting) 模式。
    
    负责：
    - 管理 LLM 对话上下文
    - 解析工具调用并执行
    - 策略校验（确认、命令黑名单）
    - 审计日志和调试追踪
    - 上下文窗口管理（历史裁剪）
    - RAG 语义搜索集成
    """
    
    def __init__(self, cfg: CludeConfig) -> None:
        """
        初始化 AgentLoop 实例。
        
        初始化流程：
        1. 创建 LLM 客户端（llama.cpp HTTP）
        2. 初始化工具集（LocalTools）
        3. 初始化审计和追踪日志
        4. 启动后台索引服务（LanceDB RAG）
        5. 生成 Repo Map（ctags）并注入系统提示词
        6. 构建初始消息历史（仅包含 system 消息）
        
        参数:
            cfg: 配置对象（包含 LLM、工作区、策略等配置）
        
        流程图: 见 `agent_loop_init_flow.svg`
        """
        self.cfg = cfg
        self.logger = get_logger(
            __name__,
            workspace_root=cfg.workspace_root,
            log_to_console=cfg.logging.log_to_console,
        )
        # 创建只写入文件的 logger（用于记录 LLM 请求/响应详情）
        self.file_only_logger = get_logger(
            f"{__name__}.llm_detail",
            workspace_root=cfg.workspace_root,
            log_to_console=False,  # 只写入文件，不输出到控制台
        )
        # keep it simple & stable enough for MVP; later replace with uuid4
        self.session_id = f"sess_{id(self)}"
        self.logger.info(f"[dim]初始化 AgentLoop，session_id={self.session_id}[/dim]")
        self.llm = LlamaCppHttpClient(
            base_url=cfg.llm.base_url,
            api_mode=cfg.llm.api_mode,  # type: ignore[arg-type]
            model=cfg.llm.model,
            temperature=cfg.llm.temperature,
            max_tokens=cfg.llm.max_tokens,
            timeout_s=cfg.llm.timeout_s,
        )
        self.tools = LocalTools(
            cfg.workspace_root,
            max_file_read_bytes=cfg.limits.max_file_read_bytes,
            max_output_bytes=cfg.limits.max_output_bytes,
        )
        self.audit = AuditLogger(cfg.workspace_root, self.session_id)
        self.trace = TraceLogger(cfg.workspace_root, self.session_id)
        
        # Knowledge / RAG systems
        self.indexer = IndexerService(cfg.workspace_root)
        self.indexer.start() # Start background indexing
        self.logger.info("[dim]启动后台索引服务（LanceDB RAG）[/dim]")
        self.embedder = CodeEmbedder()
        self.vector_store = VectorStore(cfg.workspace_root)

        # Initialize with Repo Map for better global context (Aider-style)
        import platform
        repo_map = self.tools.generate_repo_map()
        env_info = f"操作系统: {platform.system()} ({platform.release()})\n当前绝对路径: {self.cfg.workspace_root}"
        combined_system_prompt = f"{SYSTEM_PROMPT}\n\n=== 环境信息 ===\n{env_info}\n\n=== 代码仓库符号概览 ===\n{repo_map}"
        
        self.messages: list[ChatMessage] = [
            ChatMessage(role="system", content=combined_system_prompt),
        ]
        self.logger.info("[dim]初始化系统提示词（包含 Repo Map 和环境信息）[/dim]")

    def run_turn(
        self,
        user_text: str,
        *,
        confirm: Callable[[str], bool],
        debug: bool = False,
        on_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> AgentTurn:
        """
        执行一轮完整的 Agent 对话循环（ReAct 模式）。
        
        核心流程：
        1. 接收用户输入，提取关键词（用于语义窗口采样）
        2. 进入最多 20 次的工具调用循环：
           a. 调用 LLM 获取响应
           b. 检测输出异常（复读字符）
           c. 解析工具调用 JSON
           d. 如果无工具调用 → 返回最终文本
           e. 如果有工具调用 → 执行策略校验（确认/黑名单）
           f. 执行工具并获取结果
           g. 将结果回喂给 LLM（作为 user 消息）
           h. 裁剪历史消息（保持上下文窗口）
        3. 如果达到最大循环次数 → 返回停止消息
        
        参数:
            user_text: 用户输入的文本
            confirm: 确认回调函数（用于写文件/执行命令前的用户确认）
            debug: 是否启用调试模式（写入 trace.jsonl）
            on_event: 可选的事件回调（用于实时 UI 更新，如 --live 模式）
        
        返回:
            AgentTurn 对象，包含最终回复、工具使用标志、追踪ID和事件列表
        
        流程图: 见 `agent_loop_run_turn_flow.svg`
        """
        trace_id = f"trace_{abs(hash((self.session_id, user_text)))}"
        self.logger.info(f"[bold cyan]开始新的一轮对话[/bold cyan] trace_id={trace_id}")
        self.logger.info(f"[dim]用户输入: {user_text[:100]}{'...' if len(user_text) > 100 else ''}[/dim]")
        
        # Extract intent keywords for semantic windowing (MVP: simple regex)
        keywords = set(re.findall(r'\w{4,}', user_text.lower()))
        # Filter common non-useful words
        keywords -= {"please", "help", "find", "where", "change", "file", "code", "repo", "make"}
        if keywords:
            self.logger.debug(f"[dim]提取关键词: {keywords}[/dim]")
        
        events: list[dict[str, Any]] = []
        step_idx = 0

        def _ev(event: str, data: dict[str, Any]) -> None:
            nonlocal step_idx
            step_idx += 1
            e = {"step": step_idx, "event": event, "data": data}
            events.append(e)
            if debug:
                # keep trace log verbose, but trim huge fields
                self.trace.write(trace_id=trace_id, step=step_idx, event=event, data=data)
            if on_event is not None:
                try:
                    on_event(e)
                except Exception:
                    # Never allow UI callbacks to break the agent loop.
                    pass

        self.audit.write(trace_id=trace_id, event="user_message", data={"text": user_text})
        _ev("user_message", {"text": user_text})
        self.messages.append(ChatMessage(role="user", content=user_text))
        # Keep history bounded to reduce context size
        self._trim_history(max_messages=30)
        self.logger.debug(f"[dim]当前消息历史长度: {len(self.messages)}[/dim]")

        tool_used = False
        for iteration in range(20):  # hard stop to avoid infinite loops
            self.logger.info(f"[bold yellow]→ 第 {iteration + 1} 轮：请求 LLM（消息数={len(self.messages)}）[/bold yellow]")
            _ev("llm_request", {"messages": len(self.messages)})
            
            # 记录请求参数到文件（不输出到屏幕）
            request_params = {
                "model": self.llm.model,
                "temperature": self.llm.temperature,
                "max_tokens": self.llm.max_tokens,
                "api_mode": self.llm.api_mode,
                "base_url": self.llm.base_url,
                "messages_count": len(self.messages),
                "messages": [
                    {
                        "role": msg.role,
                        "content_preview": msg.content[:200] + "..." if len(msg.content) > 200 else msg.content,
                        "content_length": len(msg.content),
                    }
                    for msg in self.messages
                ],
            }
            self.file_only_logger.info(f"请求大模型参数: {json.dumps(request_params, ensure_ascii=False, indent=2)}")
            
            assistant = self.llm.chat(self.messages)
            
            # Robustness: Detect repetitive/broken outputs (stuttering)
            if assistant.count("[") > 50 or assistant.count("{") > 50:
                self.logger.warning("[red]检测到模型输出异常（复读字符），已强制截断[/red]")
                assistant = "模型输出异常：检测到过多的重复字符，已强制截断。请重新描述你的需求或尝试缩小任务范围。"
                _ev("stuttering_detected", {"length": len(assistant)})

            _ev("llm_response", {"text": assistant[:4000], "truncated": len(assistant) > 4000})
            self.logger.debug(f"[dim]LLM 响应长度: {len(assistant)} 字符[/dim]")
            
            # 解析工具调用（只解析一次）
            tool_call = _try_parse_tool_call(assistant)
            
            # 记录响应数据到文件（不输出到屏幕）
            response_data = {
                "text_length": len(assistant),
                "text_preview": assistant[:500] + "..." if len(assistant) > 500 else assistant,
                "truncated": len(assistant) > 500,
                "has_tool_call": tool_call is not None,
                "tool_call": tool_call if tool_call else None,
            }
            self.file_only_logger.info(f"大模型返回数据: {json.dumps(response_data, ensure_ascii=False, indent=2)}")
            if tool_call is None:
                self.logger.info("[bold green]✓ LLM 返回最终回复（无工具调用）[/bold green]")
                self.messages.append(ChatMessage(role="assistant", content=assistant))
                self.audit.write(trace_id=trace_id, event="assistant_text", data={"text": assistant})
                _ev("final_text", {"text": assistant[:4000], "truncated": len(assistant) > 4000})
                self._trim_history(max_messages=30)
                return AgentTurn(assistant_text=assistant, tool_used=tool_used, trace_id=trace_id, events=events)

            name = tool_call["tool"]
            args = tool_call["args"]
            self.logger.info(f"[bold blue]🔧 解析到工具调用: {name}[/bold blue]")
            self.logger.debug(f"[dim]工具参数: {json.dumps(args, ensure_ascii=False, indent=2)[:200]}[/dim]")
            _ev("tool_call_parsed", {"tool": name, "args": args})

            # Robustness: Keep assistant history clean. 
            # If there's a tool call, we only store the JSON part in the message history
            # to prevent the model from getting distracted by its own previous CoT/noise.
            clean_assistant = json.dumps(tool_call, ensure_ascii=False)
            self.messages.append(ChatMessage(role="assistant", content=clean_assistant))
            
            _ev("assistant_tool_call_recorded", {"tool": name})
            self._trim_history(max_messages=30)

            # policy confirmations (MVP): only guard write/exec
            if name in {"write_file", "apply_patch", "undo_patch"} and self.cfg.policy.confirm_write:
                self.logger.info(f"[yellow]⚠ 需要用户确认写文件操作: {name}[/yellow]")
                decision = confirm(f"确认写文件？tool={name} args={args}")
                self.audit.write(trace_id=trace_id, event="confirm_write", data={"tool": name, "args": args, "allow": decision})
                _ev("confirm_write", {"tool": name, "allow": decision})
                if not decision:
                    self.logger.warning(f"[red]✗ 用户拒绝写文件操作: {name}[/red]")
                    msg = _tool_result_to_message(name, ToolResult(False, error={"code": "E_DENIED", "message": "user denied"}), keywords=keywords)
                    self.messages.append(ChatMessage(role="user", content=msg))
                    _ev("denied_by_user", {"tool": name})
                    self._trim_history(max_messages=30)
                    continue
                else:
                    self.logger.info(f"[green]✓ 用户确认写文件操作: {name}[/green]")
            if name in {"run_cmd"} and self.cfg.policy.confirm_exec:
                self.logger.info(f"[yellow]⚠ 需要用户确认执行命令: {name}[/yellow]")
                decision = confirm(f"确认执行命令？tool={name} args={args}")
                self.audit.write(trace_id=trace_id, event="confirm_exec", data={"tool": name, "args": args, "allow": decision})
                _ev("confirm_exec", {"tool": name, "allow": decision})
                if not decision:
                    self.logger.warning(f"[red]✗ 用户拒绝执行命令: {name}[/red]")
                    msg = _tool_result_to_message(name, ToolResult(False, error={"code": "E_DENIED", "message": "user denied"}), keywords=keywords)
                    self.messages.append(ChatMessage(role="user", content=msg))
                    _ev("denied_by_user", {"tool": name})
                    self._trim_history(max_messages=30)
                    continue
                else:
                    self.logger.info(f"[green]✓ 用户确认执行命令: {name}[/green]")

            # minimal command policy (denylist)
            if name == "run_cmd":
                cmd = str(args.get("command", ""))
                dec = evaluate_command(cmd, allow_network=self.cfg.policy.allow_network)
                if not dec.ok:
                    self.logger.warning(f"[red]✗ 策略拒绝命令: {cmd} (原因: {dec.reason})[/red]")
                    self.audit.write(trace_id=trace_id, event="policy_deny_cmd", data={"command": cmd, "reason": dec.reason})
                    _ev("policy_deny_cmd", {"command": cmd, "reason": dec.reason})
                    msg = _tool_result_to_message(name, ToolResult(False, error={"code": "E_POLICY_DENIED", "message": dec.reason}), keywords=keywords)
                    self.messages.append(ChatMessage(role="user", content=msg))
                    self._trim_history(max_messages=30)
                    continue
                else:
                    self.logger.debug(f"[dim]策略检查通过: {cmd}[/dim]")

            tool_used = True
            self.logger.info(f"[bold cyan]▶ 执行工具: {name}[/bold cyan]")
            result = self._dispatch_tool(name, args)
            if result.ok:
                self.logger.info(f"[green]✓ 工具执行成功: {name}[/green]")
            else:
                self.logger.error(f"[red]✗ 工具执行失败: {name} (错误: {result.error})[/red]")
            _ev("tool_result", {"tool": name, "ok": result.ok, "error": result.error, "payload": result.payload})
            # feed tool result back to model as user message (works with most chat templates)
            self.messages.append(ChatMessage(role="user", content=_tool_result_to_message(name, result, keywords=keywords)))
            self.logger.debug(f"[dim]工具结果已回喂给 LLM[/dim]")
            _ev("tool_result_fed_back", {"tool": name})
            self._trim_history(max_messages=30)
            audit_data: dict[str, Any] = {"tool": name, "args": args, "ok": result.ok, "error": result.error}
            if name in {"apply_patch", "undo_patch"} and result.ok and result.payload:
                # record hashes/undo_id for traceability
                audit_data["payload"] = result.payload
            self.audit.write(trace_id=trace_id, event="tool_call", data=audit_data)

        self.logger.warning("[red]⚠ 达到最大工具调用次数（20），停止以避免死循环[/red]")
        _ev("stop_reason", {"reason": "max_tool_calls_reached", "limit": 20})
        return AgentTurn(
            assistant_text="达到本轮最大工具调用次数（20），已停止以避免死循环。请缩小任务或提供更多约束/入口文件。",
            tool_used=tool_used,
            trace_id=trace_id,
            events=events,
        )

    def _trim_history(self, *, max_messages: int) -> None:
        """
        裁剪对话历史，保持上下文窗口在合理范围内。
        
        裁剪策略：
        1. 始终保留第一条 system 消息（包含核心指令和 Repo Map）
        2. 从尾部向前裁剪，但确保裁剪后的第一条消息是 'user' 角色
           （满足 llama.cpp 等严格 chat template 的 user/assistant 交替要求）
        3. 如果当前消息数 <= max_messages，则不进行裁剪
        
        参数:
            max_messages: 最大保留消息数（包括 system 消息）
        
        流程图: 见 `agent_loop_trim_history_flow.svg`
        """
        old_len = len(self.messages)
        if old_len <= max_messages:
            return
        
        system = self.messages[0]
        # We need an odd number of messages in the tail if the last one is 'user'
        # or just ensure the first message of the tail is 'user'.
        tail_start_idx = len(self.messages) - (max_messages - 1)
        
        # Move forward until we find a 'user' message to keep parity
        while tail_start_idx < len(self.messages) and self.messages[tail_start_idx].role != "user":
            tail_start_idx += 1
            
        tail = self.messages[tail_start_idx:]
        self.messages = [system, *tail]
        self.logger.debug(f"[dim]历史裁剪: {old_len} → {len(self.messages)} 条消息[/dim]")

    def _dispatch_tool(self, name: str, args: dict[str, Any]) -> ToolResult:
        """
        根据工具名称分发到对应的工具执行函数。
        
        支持的工具：
        - list_dir: 列出目录内容
        - read_file: 读取文件（支持 offset/limit）
        - glob_file_search: 按模式搜索文件
        - grep: 文本搜索（优先 ripgrep，降级 Python）
        - apply_patch: 应用代码补丁（支持模糊匹配）
        - undo_patch: 回滚补丁（基于 undo_id）
        - write_file: 写入文件
        - run_cmd: 执行命令
        - search_semantic: 语义搜索（向量 RAG）
        
        参数:
            name: 工具名称
            args: 工具参数字典
        
        返回:
            ToolResult 对象（包含 ok/error/payload）
        
        异常处理:
            - KeyError: 缺少必需参数 → 返回 E_INVALID_ARGS
            - 其他异常: 工具执行失败 → 返回 E_TOOL
        
        流程图: 见 `agent_loop_dispatch_tool_flow.svg`
        """
        try:
            if name == "list_dir":
                return self.tools.list_dir(path=args.get("path", "."))
            if name == "read_file":
                return self.tools.read_file(path=args["path"], offset=args.get("offset"), limit=args.get("limit"))
            if name == "glob_file_search":
                return self.tools.glob_file_search(glob_pattern=args["glob_pattern"], target_directory=args.get("target_directory", "."))
            if name == "grep":
                return self.tools.grep(
                    pattern=args["pattern"],
                    path=args.get("path", "."),
                    ignore_case=bool(args.get("ignore_case", False)),
                    max_hits=int(args.get("max_hits", 200)),
                )
            if name == "apply_patch":
                return self.tools.apply_patch(
                    path=args["path"],
                    old=args["old"],
                    new=args["new"],
                    expected_replacements=int(args.get("expected_replacements", 1)),
                    fuzzy=bool(args.get("fuzzy", False)),
                    min_similarity=float(args.get("min_similarity", 0.92)),
                )
            if name == "undo_patch":
                return self.tools.undo_patch(
                    undo_id=args["undo_id"],
                    force=bool(args.get("force", False)),
                )
            if name == "write_file":
                return self.tools.write_file(path=args["path"], text=args.get("text", ""))
            if name == "run_cmd":
                return self.tools.run_cmd(command=args["command"], cwd=args.get("cwd", "."))
            if name == "search_semantic":
                return self._semantic_search(query=args["query"])
            return ToolResult(False, error={"code": "E_NO_TOOL", "message": f"unknown tool: {name}"})
        except KeyError as e:
            return ToolResult(False, error={"code": "E_INVALID_ARGS", "message": f"missing arg: {e}"})
        except Exception as e:
            return ToolResult(False, error={"code": "E_TOOL", "message": str(e)})

    def _semantic_search(self, query: str) -> ToolResult:
        """
        执行语义搜索（向量 RAG）。
        
        流程：
        1. 使用 CodeEmbedder 将查询文本转换为向量
        2. 在 VectorStore（LanceDB）中搜索最相似的代码块（top 5）
        3. 将搜索结果格式化为 ToolResult
        
        参数:
            query: 搜索查询文本（自然语言）
        
        返回:
            ToolResult 对象，payload 包含：
            - query: 原始查询
            - hits: 搜索结果列表（每个包含 path/start_line/end_line/text）
        
        异常处理:
            任何异常都会返回 E_SEMANTIC_SEARCH 错误
        
        流程图: 见 `agent_loop_semantic_search_flow.svg`
        """
        try:
            self.logger.debug(f"[dim]执行语义搜索: {query[:50]}...[/dim]")
            q_vector = self.embedder.embed_query(query)
            hits = self.vector_store.search(q_vector, limit=5)
            self.logger.info(f"[green]✓ 语义搜索找到 {len(hits)} 个结果[/green]")
            
            payload_hits = []
            for h in hits:
                payload_hits.append({
                    "path": h.get("path"),
                    "start_line": h.get("start_line"),
                    "end_line": h.get("end_line"),
                    "text": h.get("text")
                })
            
            return ToolResult(True, payload={"query": query, "hits": payload_hits})
        except Exception as e:
            self.logger.error(f"[red]✗ 语义搜索失败: {e}[/red]")
            return ToolResult(False, error={"code": "E_SEMANTIC_SEARCH", "message": str(e)})


