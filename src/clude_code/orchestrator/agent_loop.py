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
from clude_code.verification.runner import Verifier
from clude_code.orchestrator.planner import parse_plan_from_text, render_plan_markdown, Plan
from clude_code.orchestrator.state_m import AgentState
from clude_code.orchestrator.classifier import IntentClassifier, IntentCategory


SYSTEM_PROMPT = """\
# 核心元规则 (META-RULES) - 优先级最高
1. **身份锚定**：你是一个名为 clude-code 的【高级软件架构工程师】。你不是对话助手，严禁表现得像个高级软件架构工程师。
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
- 当涉及“评分”时，必须对比的业界标准。
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
        self.verifier = Verifier(cfg.workspace_root)
        self.classifier = IntentClassifier(self.llm, file_only_logger=self.file_only_logger)

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

        keywords = self._extract_keywords(user_text)

        events: list[dict[str, Any]] = []
        step_idx = 0

        def _ev(event: str, data: dict[str, Any]) -> None:
            nonlocal step_idx
            step_idx += 1
            e = {"step": step_idx, "event": event, "data": data}
            events.append(e)
            if debug:
                self.trace.write(trace_id=trace_id, step=step_idx, event=event, data=data)
            if on_event is not None:
                try:
                    on_event(e)
                except Exception:
                    pass

        current_state: AgentState = AgentState.INTAKE

        def _set_state(state: AgentState, info: dict[str, Any] | None = None) -> None:
            nonlocal current_state
            current_state = state
            payload = {"state": state.value}
            if info:
                payload.update(info)
            _ev("state", payload)

        # 1) Intake + Intent 分类（决策门）
        _set_state(AgentState.INTAKE, {"step": "classifying"})
        enable_planning = self._classify_intent_and_decide_planning(user_text, _ev)
        planning_prompt = self._build_planning_prompt() if enable_planning else None

        # 2) 记录用户输入（必要时把规划提示并入同一条 user 消息，避免 role 不交替）
        self.audit.write(trace_id=trace_id, event="user_message", data={"text": user_text})
        _ev("user_message", {"text": user_text})
        user_content = user_text if not planning_prompt else (user_text + "\n\n" + planning_prompt)
        self.messages.append(ChatMessage(role="user", content=user_content))
        self._trim_history(max_messages=30)
        self.logger.debug(f"[dim]当前消息历史长度: {len(self.messages)}[/dim]")

        llm_chat = (lambda stage, step_id=None: self._llm_chat(stage, step_id=step_id, _ev=_ev))

        # 3) 规划阶段
        plan: Plan | None = None
        if enable_planning:
            _set_state(AgentState.PLANNING, {"reason": "enable_planning"})
            plan = self._execute_planning_phase(user_text, planning_prompt, trace_id, _ev, llm_chat)

        # 4) 执行阶段
        if plan is not None:
            plan, tool_used, did_modify_code = self._execute_plan_steps(
                plan,
                trace_id,
                keywords,
                confirm,
                events,
                _ev,
                llm_chat,
                _try_parse_tool_call,
                _tool_result_to_message,
                _set_state,
            )

            if plan is None:
                stop_reason = None
                for e in reversed(events):
                    if e.get("event") == "stop_reason":
                        stop_reason = e.get("data", {}).get("reason")
                        break

                if stop_reason == "max_replans_reached":
                    text = "达到最大重规划次数，已停止。请缩小任务或提供更明确的入口文件/目标。"
                elif stop_reason == "dependency_deadlock":
                    text = "检测到依赖死锁：所有未完成步骤都处于 blocked 状态。请检查计划中的依赖关系。"
                elif stop_reason == "step_not_completed":
                    text = "步骤未能完成且未触发重规划。请缩小该步骤或提供更多约束。"
                elif stop_reason == "replan_parse_failed":
                    text = "重规划失败（无法解析 Plan JSON）。请手动提供更明确的拆分步骤或入口文件。"
                else:
                    text = "执行阶段提前退出。"

                return AgentTurn(assistant_text=text, tool_used=tool_used, trace_id=trace_id, events=events)

            final_result = self._execute_final_verification(plan, did_modify_code, trace_id, tool_used, _ev, _set_state)
            if final_result is not None:
                final_result.events = events
                return final_result

            _set_state(AgentState.DONE, {"ok": True})
            return AgentTurn(
                assistant_text=f"计划执行完成：{plan.title}\n（已按步骤执行并完成自检）",
                tool_used=tool_used,
                trace_id=trace_id,
                events=events,
            )

        # 5) ReAct fallback
        return self._execute_react_fallback_loop(
            trace_id=trace_id,
            keywords=keywords,
            confirm=confirm,
            events=events,
            _ev=_ev,
            _llm_chat=llm_chat,
            _try_parse_tool_call=_try_parse_tool_call,
            _tool_result_to_message=_tool_result_to_message,
            _set_state=_set_state,
        )

    def _extract_keywords(self, user_text: str) -> set[str]:
        """提取用户输入中的关键词（用于语义窗口采样）。"""
        keywords = set(re.findall(r'\w{4,}', user_text.lower()))
        keywords -= {"please", "help", "find", "where", "change", "file", "code", "repo", "make"}
        if keywords:
            self.logger.debug(f"[dim]提取关键词: {keywords}[/dim]")
        return keywords

    def _normalize_messages_for_llama(self, stage: str, *, step_id: str | None = None, _ev: Callable[[str, dict[str, Any]], None] | None = None) -> None:
        """
        发送给 llama.cpp 前的"统一出口"规范化：
        - 合并连续的 user/user 或 assistant/assistant（避免 chat template 报 500）
        - 合并多条 system 到第一条 system（避免 system/system 或 system 插入导致不交替）
        - 如果 system 后意外出现 assistant，则并入 system（保持严格 alternation）
        """
        if not self.messages:
            return

        original_len = len(self.messages)
        merged_pairs = 0
        merged_system = 0
        merged_into_system_from_assistant = 0

        # 1) 保留/合并 system
        system_msg: ChatMessage | None = None
        idx = 0
        if self.messages[0].role == "system":
            system_msg = self.messages[0]
            idx = 1

        out: list[ChatMessage] = []
        if system_msg is not None:
            out.append(system_msg)

        expected = "user"  # system 后必须从 user 开始

        # 2) 逐条规范化
        for m in self.messages[idx:]:
            role = m.role
            content = m.content

            # 多 system：并入第一条 system
            if role == "system":
                if out and out[0].role == "system":
                    merged_system += 1
                    out[0] = ChatMessage(role="system", content=out[0].content + "\n\n" + content)
                    continue
                out.insert(0, m)
                continue

            # system 后出现 assistant（不符合严格模板）：并入 system
            if expected == "user" and (not out or out[-1].role == "system") and role == "assistant":
                if out and out[0].role == "system":
                    merged_into_system_from_assistant += 1
                    out[0] = ChatMessage(role="system", content=out[0].content + "\n\n" + "[历史 assistant 前置信息]\n" + content)
                    continue
                merged_pairs += 1
                continue

            # 正常交替：按 expected 接入
            if role == expected:
                out.append(m)
                expected = "assistant" if expected == "user" else "user"
                continue

            # 非预期角色：只可能是连续 user/user 或 assistant/assistant
            if out and out[-1].role == role:
                merged_pairs += 1
                out[-1] = ChatMessage(role=role, content=out[-1].content + "\n\n" + content)
                continue

            # 兜底：无法解释的顺序，尽量并入上一条（避免新增破坏交替）
            if out:
                merged_pairs += 1
                out[-1] = ChatMessage(role=out[-1].role, content=out[-1].content + "\n\n" + content)
                continue

        # 3) 若发生变化，回写 self.messages，并上报事件用于 UI/调试
        if len(out) != original_len or merged_pairs or merged_system or merged_into_system_from_assistant:
            self.messages = out
            self._trim_history(max_messages=30)
            if _ev:
                _ev("messages_normalized", {
                    "stage": stage,
                    "step_id": step_id,
                    "before": original_len,
                    "after": len(self.messages),
                    "merged_pairs": merged_pairs,
                    "merged_system": merged_system,
                    "merged_assistant_into_system": merged_into_system_from_assistant,
                })

    def _llm_chat(self, stage: str, *, step_id: str | None = None, _ev: Callable[[str, dict[str, Any]], None] | None = None) -> str:
        """llama.cpp 调用统一出口：先做 messages 规范化，再发起 HTTP 请求。"""
        self._normalize_messages_for_llama(stage, step_id=step_id, _ev=_ev)
        return self.llm.chat(self.messages)

    def _build_planning_prompt(self) -> str:
        """
        构建规划阶段提示词（并入 user 消息，避免 user/user 连续导致 llama.cpp 报错）。

        注意：
        - 这里输出的是“提示词文本”，不是消息对象。
        - `run_turn` 会把它拼到用户输入后面，作为同一条 user 消息发送。
        """
        return (
            "现在进入【规划阶段】。请先输出一个严格的 JSON 对象（不要输出任何解释、不要调用工具）。\n"
            "JSON 必须符合以下结构：\n"
            "{\n"
            '  "title": "任务全局目标",\n'
            '  "steps": [\n'
            "    {\n"
            '      "id": "step_1",\n'
            '      "description": "可执行且可验证的动作（可跨文件）",\n'
            '      "dependencies": [],\n'
            '      "status": "pending",\n'
            '      "tools_expected": ["read_file","grep","apply_patch"]\n'
            "    }\n"
            "  ],\n"
            '  "verification_policy": "run_verify"\n'
            "}\n\n"
            f"要求：steps 不超过 {self.cfg.orchestrator.max_plan_steps} 步；每步尽量小且明确。"
        )

    def _log_llm_request_params_to_file(self) -> None:
        """把本次 LLM 请求参数（含 messages 摘要）写入 file_only_logger。"""
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

    def _log_llm_response_data_to_file(self, assistant_text: str, tool_call: dict[str, Any] | None) -> None:
        """把本次 LLM 返回数据摘要写入 file_only_logger。"""
        response_data = {
            "text_length": len(assistant_text),
            "text_preview": assistant_text[:500] + "..." if len(assistant_text) > 500 else assistant_text,
            "truncated": len(assistant_text) > 500,
            "has_tool_call": tool_call is not None,
            "tool_call": tool_call if tool_call else None,
        }
        self.file_only_logger.info(f"大模型返回数据: {json.dumps(response_data, ensure_ascii=False, indent=2)}")

    def _run_tool_lifecycle(
        self,
        name: str,
        args: dict[str, Any],
        trace_id: str,
        confirm: Callable[[str], bool],
        _ev: Callable[[str, dict[str, Any]], None],
    ) -> ToolResult:
        """
        统一工具执行生命周期：策略检查 -> 确认 -> 审计 -> 执行 -> 验证。
        """
        # 1. 确认策略 (MVP: 写/执行 确认)
        if name in {"write_file", "apply_patch", "undo_patch"} and self.cfg.policy.confirm_write:
            self.logger.info(f"[yellow]⚠ 需要用户确认写文件操作: {name}[/yellow]")
            if not confirm(f"确认写文件？tool={name} args={args}"):
                self.logger.warning(f"[red]✗ 用户拒绝写文件操作: {name}[/red]")
                self.audit.write(trace_id=trace_id, event="confirm_deny", data={"tool": name, "args": args})
                _ev("denied_by_user", {"tool": name})
                return ToolResult(ok=False, error={"code": "E_DENIED", "message": "User denied write access"})
            else:
                self.logger.info(f"[green]✓ 用户确认写文件操作: {name}[/green]")

        if name == "run_cmd":
            cmd = str(args.get("command", ""))
            # 内部安全评估（黑名单）
            decision = evaluate_command(cmd, allow_network=self.cfg.policy.allow_network)
            if not decision.ok:
                self.logger.warning(f"[red]✗ 策略拒绝命令: {cmd} (原因: {decision.reason})[/red]")
                self.audit.write(trace_id=trace_id, event="policy_deny_cmd", data={"command": cmd, "reason": decision.reason})
                _ev("policy_deny_cmd", {"command": cmd, "reason": decision.reason})
                return ToolResult(ok=False, error={"code": "E_POLICY", "message": decision.reason})
            # 用户交互确认
            if self.cfg.policy.confirm_exec:
                self.logger.info(f"[yellow]⚠ 需要用户确认执行命令: {cmd}[/yellow]")
                if not confirm(f"确认执行命令？{cmd}"):
                    self.logger.warning(f"[red]✗ 用户拒绝执行命令: {cmd}[/red]")
                    self.audit.write(trace_id=trace_id, event="confirm_deny", data={"tool": name, "command": cmd})
                    _ev("denied_by_user", {"tool": name})
                    return ToolResult(ok=False, error={"code": "E_DENIED", "message": "User denied command execution"})
                else:
                    self.logger.info(f"[green]✓ 用户确认执行命令[/green]")

        # 2. 核心执行
        self.logger.info(f"[bold cyan]▶ 执行工具: {name}[/bold cyan]")
        result = self._dispatch_tool(name, args)

        # 详细日志输出
        result_summary = self._format_result_summary(name, result)
        if result.ok:
            self.logger.info(f"[green]✓ 工具执行成功: {name}[/green] [结果] {result_summary}")
        else:
            error_msg = result.error.get("message", str(result.error)) if isinstance(result.error, dict) else str(result.error)
            self.logger.error(f"[red]✗ 工具执行失败: {name}[/red] [错误] {error_msg} [结果] {result_summary}")

        # 3. 记录审计
        audit_data: dict[str, Any] = {"tool": name, "args": args, "ok": result.ok, "error": result.error}
        if name in {"apply_patch", "undo_patch"} and result.ok and result.payload:
            audit_data["payload"] = result.payload  # 记录 hash/undo_id
        self.audit.write(trace_id=trace_id, event="tool_call", data=audit_data)
        
        # 4. 记录详细结果到文件
        self.file_only_logger.info(
            f"工具执行结果 [tool={name}] [ok={result.ok}] "
            f"[error={json.dumps(result.error, ensure_ascii=False) if result.error else None}] "
            f"[payload_keys={list(result.payload.keys()) if result.payload else []}]"
        )

        # 5. 自动化验证闭环 (自愈)
        if result.ok and name in {"write_file", "apply_patch", "undo_patch", "run_cmd"}:
            self.logger.info("[bold magenta]🔍 自动触发验证闭环...[/bold magenta]")
            v_res = self.verifier.run_verify()
            _ev("autofix_check", {"ok": v_res.ok, "type": v_res.type, "summary": v_res.summary})
            
            if v_res.ok:
                self.logger.info(f"[green]✓ 验证通过[/green] [摘要] {v_res.summary}")
            else:
                error_details = "; ".join([f"{err.file}:{err.line} {err.message}" for err in (v_res.errors or [])[:3]])
                self.logger.warning(f"[yellow]⚠ 验证失败[/yellow] [摘要] {v_res.summary} [错误] {error_details}")
                self.file_only_logger.warning(
                    f"验证失败详情 [tool={name}] [errors={json.dumps([{'file': err.file, 'line': err.line, 'message': err.message} for err in (v_res.errors or [])], ensure_ascii=False)}]"
                )
                # 注入验证失败信息到结果 payload
                v_msg = f"\n\n[验证失败 - 自动自检结果]\n状态: {v_res.summary}\n"
                if v_res.errors:
                    v_msg += "具体错误:\n"
                    for err in v_res.errors[:3]:
                        v_msg += f"- {err.file}:{err.line} {err.message}\n"
                if result.payload is None:
                    result = ToolResult(ok=True, payload={"verification_error": v_msg})
                else:
                    result.payload["verification_error"] = v_msg

        return result

    def _classify_intent_and_decide_planning(self, user_text: str, _ev: Callable[[str, dict[str, Any]], None]) -> bool:
        """意图分类和决策门：根据用户意图决定是否启用规划。"""
        classification = self.classifier.classify(user_text)
        self.logger.info(f"[bold cyan]意图识别结果: {classification.category.value}[/bold cyan] (置信度: {classification.confidence})")
        _ev("intent_classified", classification.model_dump())

        enable_planning = self.cfg.orchestrator.enable_planning
        if classification.category in (IntentCategory.CAPABILITY_QUERY, IntentCategory.GENERAL_CHAT):
            if enable_planning:
                self.logger.info("[dim]检测到能力询问或通用对话，跳过显式规划阶段。[/dim]")
                enable_planning = False
        return enable_planning

    def _execute_planning_phase(self, user_text: str, planning_prompt: str | None, trace_id: str, _ev: Callable[[str, dict[str, Any]], None], _llm_chat: Callable[[str, str | None], str]) -> Plan | None:
        """执行规划阶段：生成显式 Plan。"""
        if not planning_prompt:
            return None

        _ev("state", {"state": AgentState.PLANNING.value, "reason": "enable_planning"})
        self.logger.info("[bold magenta]🧩 进入规划阶段：生成显式 Plan[/bold magenta]")

        plan_attempts = 0
        while plan_attempts <= self.cfg.orchestrator.planning_retry:
            plan_attempts += 1
            _ev("planning_llm_request", {"attempt": plan_attempts})
            assistant_plan = _llm_chat("planning", None)
            _ev("planning_llm_response", {"text": assistant_plan[:4000], "truncated": len(assistant_plan) > 4000})

            self.messages.append(ChatMessage(role="assistant", content=assistant_plan))
            self._trim_history(max_messages=30)
            try:
                parsed = parse_plan_from_text(assistant_plan)
                if len(parsed.steps) > self.cfg.orchestrator.max_plan_steps:
                    parsed.steps = parsed.steps[: self.cfg.orchestrator.max_plan_steps]
                plan = parsed
                # 完善：强制执行 ID 唯一性校验，防止 LLM 生成重复步骤导致逻辑混乱
                try:
                    plan.validate_unique_ids()
                except ValueError as ve:
                    # 自动尝试修复：如果发现重复 ID，则重新生成或抛出异常触发重试
                    self.logger.warning(f"[yellow]🧩 计划步骤 ID 重复，尝试进入重试逻辑: {ve}[/yellow]")
                    raise ve

                self.audit.write(trace_id=trace_id, event="plan_generated", data={"title": plan.title, "steps": [s.model_dump() for s in plan.steps]})
                _ev("plan_generated", {"title": plan.title, "steps": len(plan.steps)})
                self.logger.info("[green]✓ 计划生成成功[/green]")
                plan_summary = render_plan_markdown(plan)
                self.logger.info(f"[dim]计划摘要:\n{plan_summary}[/dim]")
                self.file_only_logger.info("生成计划:\n" + plan_summary)
                return plan
            except Exception as e:
                self.logger.warning(f"[yellow]⚠ 计划解析失败（attempt={plan_attempts}）: {e}[/yellow]")
                self.audit.write(trace_id=trace_id, event="plan_parse_failed", data={"attempt": plan_attempts, "error": str(e)})
                _ev("plan_parse_failed", {"attempt": plan_attempts, "error": str(e)})
                self.messages.append(ChatMessage(role="user", content="上面的输出无法解析为 Plan JSON。请只输出一个严格 JSON 对象（不要解释，不要代码块）。"))
                self._trim_history(max_messages=30)
        return None

    def _check_step_dependencies(self, step, plan: Plan, trace_id: str, _ev: Callable[[str, dict[str, Any]], None]) -> list[str]:
        """检查步骤依赖是否满足，如果不满足则标记为 blocked。"""
        completed_ids = {s.id for s in plan.steps if s.status == "done"}
        unmet_deps = [dep for dep in step.dependencies if dep not in completed_ids]
        if unmet_deps:
            self.logger.warning(f"[yellow]⚠ 步骤 {step.id} 有未满足的依赖: {unmet_deps}，跳过并标记为 blocked[/yellow]")
            step.status = "blocked"
            self.audit.write(trace_id=trace_id, event="plan_step_blocked", data={"step_id": step.id, "unmet_deps": unmet_deps})
            _ev("plan_step_blocked", {"step_id": step.id, "unmet_deps": unmet_deps})
        return unmet_deps

    def _handle_tool_call_in_step(
        self,
        name: str,
        args: dict[str, Any],
        step,
        trace_id: str,
        keywords: set[str],
        confirm: Callable[[str], bool],
        _ev: Callable[[str, dict[str, Any]], None],
        _tool_result_to_message: Callable[[str, ToolResult, set[str] | None], str],
    ) -> tuple[ToolResult, bool]:
        """
        处理步骤中的工具调用：确认、策略检查、执行、验证。
        返回: (result, did_modify_code)
        """
        # 调用统一生命周期
        result = self._run_tool_lifecycle(name, args, trace_id, confirm, _ev)

        # 判断是否修改了代码
        did_modify_code = (name in {"write_file", "apply_patch", "undo_patch"} and result.ok)

        # 记录步骤关联的结果
        _ev("tool_result", {"tool": name, "ok": result.ok, "error": result.error, "payload": result.payload, "step_id": step.id})
        
        # 回馈结果
        result_msg = _tool_result_to_message(name, result, keywords=keywords)
        self.messages.append(ChatMessage(role="user", content=result_msg))
        self.logger.debug(f"[dim]工具结果已回喂[/dim] [工具] {name} [步骤] {step.id}")
        self.file_only_logger.debug(f"工具结果回喂 [step={step.id}] [tool={name}] [len={len(result_msg)}]")
        _ev("tool_result_fed_back", {"tool": name})
        self._trim_history(max_messages=30)
        
        return result, did_modify_code

    def _execute_single_step_iteration(
        self,
        step,
        step_cursor: int,
        plan: Plan,
        iteration: int,
        trace_id: str,
        keywords: set[str],
        confirm: Callable[[str], bool],
        _ev: Callable[[str, dict[str, Any]], None],
        _llm_chat: Callable[[str, str | None], str],
        _try_parse_tool_call: Callable[[str], dict[str, Any] | None],
        _tool_result_to_message: Callable[[str, ToolResult, set[str] | None], str],
    ) -> tuple[str | None, bool, bool]:
        """
        执行单个计划步骤的一次 LLM 交互轮次。
        返回: (control_signal, did_modify_code, did_use_tool)
        """
        tools_hint = ", ".join(step.tools_expected) if step.tools_expected else "（未指定，模型自选）"
        self.logger.info(
            f"[bold yellow]→ 执行步骤 {step_cursor + 1}/{len(plan.steps)}: {step.id}（轮次 {iteration + 1}/{self.cfg.orchestrator.max_step_tool_calls}）[/bold yellow] "
            f"[描述] {step.description} [建议工具] {tools_hint}"
        )
        _ev("llm_request", {"messages": len(self.messages), "step_id": step.id, "iteration": iteration + 1})

        # 记录请求参数到文件
        self._log_llm_request_params_to_file()

        step_prompt = (
            f"现在执行计划步骤：{step.id}\n"
            f"步骤描述：{step.description}\n"
            f"建议工具：{', '.join(step.tools_expected) if step.tools_expected else '（自行选择）'}\n\n"
            "规则：\n"
            "1) 如果需要工具：只输出一个工具调用 JSON（与系统要求一致）。\n"
            "2) 如果本步骤已完成且不需要工具：只输出字符串【STEP_DONE】。\n"
            "3) 如果本步骤失败且需要重规划：只输出字符串【REPLAN】。\n"
        )
        self.messages.append(ChatMessage(role="user", content=step_prompt))
        self._trim_history(max_messages=30)

        assistant = _llm_chat("execute_step", step.id)
        _ev("llm_response", {"text": assistant[:4000], "truncated": len(assistant) > 4000, "step_id": step.id})

        # stuttering 防护
        if assistant.count("[") > 50 or assistant.count("{") > 50:
            self.logger.warning("[red]检测到模型输出异常（复读字符），已强制截断[/red]")
            assistant = "模型输出异常：检测到过多的重复字符，已强制截断。"
            _ev("stuttering_detected", {"length": len(assistant), "step_id": step.id})

        # 检查控制标记
        a_strip = assistant.strip()
        if "STEP_DONE" in a_strip or "【STEP_DONE】" in a_strip or a_strip.upper().startswith("STEP_DONE"):
            self.messages.append(ChatMessage(role="assistant", content=assistant))
            self._trim_history(max_messages=30)
            step.status = "done"
            self.audit.write(trace_id=trace_id, event="plan_step_done", data={"step_id": step.id})
            _ev("plan_step_done", {"step_id": step.id})
            self.logger.info(f"[green]✓ 步骤完成[/green] [步骤] {step.id} [描述] {step.description} [轮次] {iteration + 1}/{self.cfg.orchestrator.max_step_tool_calls}")
            self.file_only_logger.info(f"步骤完成详情 [step_id={step.id}] [description={step.description}] [iteration={iteration + 1}]")
            return "STEP_DONE", False, False

        if "REPLAN" in a_strip or "【REPLAN】" in a_strip or a_strip.upper().startswith("REPLAN"):
            self.messages.append(ChatMessage(role="assistant", content=assistant))
            self._trim_history(max_messages=30)
            step.status = "failed"
            self.audit.write(trace_id=trace_id, event="plan_step_replan_requested", data={"step_id": step.id})
            _ev("plan_step_replan_requested", {"step_id": step.id})
            self.logger.warning(f"[yellow]⚠ 步骤请求重规划[/yellow] [步骤] {step.id} [描述] {step.description} [轮次] {iteration + 1}/{self.cfg.orchestrator.max_step_tool_calls} [原因] 模型输出【REPLAN】标记")
            self.file_only_logger.info(f"步骤请求重规划详情 [step_id={step.id}] [description={step.description}] [iteration={iteration + 1}]")
            return "REPLAN", False, False

        # 尝试解析工具调用
        tool_call = _try_parse_tool_call(assistant)
        
        # 记录响应数据到文件
        self._log_llm_response_data_to_file(assistant, tool_call)

        if tool_call is None:
            self.messages.append(ChatMessage(role="assistant", content=assistant))
            self._trim_history(max_messages=30)
            self.messages.append(ChatMessage(role="user", content="你的输出既不是工具调用 JSON，也不是【STEP_DONE】/【REPLAN】。请严格按规则输出。"))
            self._trim_history(max_messages=30)
            return None, False, False

        name = tool_call["tool"]
        args = tool_call["args"]
        _ev("tool_call_parsed", {"tool": name, "args": args, "step_id": step.id})
        
        args_summary = self._format_args_summary(name, args)
        self.logger.info(f"[bold blue]🔧 解析到工具调用: {name}[/bold blue] [步骤] {step.id} [参数] {args_summary}")
        self.file_only_logger.info(f"工具调用详情 [step_id={step.id}] [tool={name}] [args={json.dumps(args, ensure_ascii=False)}]")

        clean_assistant = json.dumps(tool_call, ensure_ascii=False)
        self.messages.append(ChatMessage(role="assistant", content=clean_assistant))
        self._trim_history(max_messages=30)

        # 处理工具调用
        result, did_modify_code = self._handle_tool_call_in_step(name, args, step, trace_id, keywords, confirm, _ev, _tool_result_to_message)
        if result is None:
            # 用户拒绝或策略拦截，此时虽然尝试了调用，但实际未执行成功，记录为已使用过工具（轮次消耗）
            return None, False, True

        return None, did_modify_code, True

    def _handle_replanning(
        self,
        step,
        plan: Plan,
        replans_used: int,
        trace_id: str,
        tool_used: bool,
        _ev: Callable[[str, dict[str, Any]], None],
        _llm_chat: Callable[[str, str | None], str],
        _set_state: Callable[[AgentState, dict[str, Any] | None], None],
    ) -> tuple[Plan | None, int]:
        """处理重规划逻辑。返回: (new_plan, new_replans_used)"""
        if replans_used >= self.cfg.orchestrator.max_replans:
            self.logger.warning(f"[red]⚠ 达到最大重规划次数，停止[/red] [当前步骤] {step.id} [描述] {step.description} [已用重规划] {replans_used}/{self.cfg.orchestrator.max_replans}")
            self.file_only_logger.warning(f"达到最大重规划次数 [step_id={step.id}] [replans_used={replans_used}] [max_replans={self.cfg.orchestrator.max_replans}]")
            _ev("stop_reason", {"reason": "max_replans_reached", "limit": self.cfg.orchestrator.max_replans})
            return None, replans_used

        replans_used += 1
        _set_state(AgentState.RECOVERING, {"reason": "step_failed", "step_id": step.id, "replans_used": replans_used})
        _set_state(AgentState.PLANNING, {"reason": "replan", "replans_used": replans_used})
        completed_count = len([s for s in plan.steps if s.status == "done"])
        self.logger.info(f"[bold magenta]🔁 触发重规划（第 {replans_used} 次）[/bold magenta] [失败步骤] {step.id} [描述] {step.description} [已完成步骤] {completed_count}/{len(plan.steps)}")
        self.file_only_logger.info(f"触发重规划 [replans_used={replans_used}] [failed_step_id={step.id}] [description={step.description}] [completed_steps={completed_count}/{len(plan.steps)}]")

        replan_prompt = (
            "出现阻塞/失败，需要重规划。请输出新的 Plan JSON（严格 JSON，不要解释，不要调用工具）。\n"
            f"限制：steps 不超过 {self.cfg.orchestrator.max_plan_steps}。\n"
            "请结合当前对话中的错误与工具反馈，生成更可执行的步骤。"
        )
        self.messages.append(ChatMessage(role="user", content=replan_prompt))
        self._trim_history(max_messages=30)
        assistant_plan = _llm_chat("replan", step.id)
        self.messages.append(ChatMessage(role="assistant", content=assistant_plan))
        self._trim_history(max_messages=30)
        
        try:
            new_plan = parse_plan_from_text(assistant_plan)
            if len(new_plan.steps) > self.cfg.orchestrator.max_plan_steps:
                new_plan.steps = new_plan.steps[: self.cfg.orchestrator.max_plan_steps]
            self.audit.write(trace_id=trace_id, event="plan_replanned", data={"title": new_plan.title, "steps": [s.model_dump() for s in new_plan.steps], "replans_used": replans_used})
            _ev("plan_replanned", {"title": new_plan.title, "steps": len(new_plan.steps), "replans_used": replans_used})
            plan_summary = render_plan_markdown(new_plan)
            self.logger.info(f"[green]✓ 重规划成功[/green] [标题] {new_plan.title} [步骤数] {len(new_plan.steps)} [重规划次数] {replans_used}/{self.cfg.orchestrator.max_replans}")
            self.file_only_logger.info(f"重规划成功 [title={new_plan.title}] [steps={len(new_plan.steps)}] [replans_used={replans_used}] [plan_summary={plan_summary[:500]}]")
            _set_state(AgentState.EXECUTING, {"steps": len(new_plan.steps)})
            return new_plan, replans_used
        except Exception as e:
            self.logger.warning(f"[yellow]⚠ 重规划解析失败[/yellow] [错误] {str(e)} [重规划次数] {replans_used}/{self.cfg.orchestrator.max_replans}")
            self.file_only_logger.exception(f"重规划解析失败 [replans_used={replans_used}] [error={str(e)}]", exc_info=True)
            self.audit.write(trace_id=trace_id, event="plan_replan_parse_failed", data={"error": str(e)})
            _ev("plan_replan_parse_failed", {"error": str(e)})
            _ev("stop_reason", {"reason": "replan_parse_failed", "error": str(e)})
            return None, replans_used

    def _execute_final_verification(self, plan: Plan, did_modify_code: bool, trace_id: str, tool_used: bool, _ev: Callable[[str, dict[str, Any]], None], _set_state: Callable[[AgentState, dict[str, Any] | None], None]) -> AgentTurn | None:
        """执行最终验证阶段。如果验证失败，返回 AgentTurn；否则返回 None。"""
        _set_state(AgentState.VERIFYING, {"did_modify_code": did_modify_code})
        if not did_modify_code:
            return None

        self.logger.info(f"[bold magenta]🔍 进入最终验证阶段[/bold magenta] [已完成步骤] {len([s for s in plan.steps if s.status == 'done'])}/{len(plan.steps)}")
        v_res = self.verifier.run_verify()
        _ev("final_verify", {"ok": v_res.ok, "type": v_res.type, "summary": v_res.summary})
        
        if v_res.ok:
            self.logger.info(f"[green]✓ 最终验证通过[/green] [类型] {v_res.type} [摘要] {v_res.summary}")
        else:
            error_details = "; ".join([f"{err.file}:{err.line} {err.message}" for err in (v_res.errors or [])[:5]])
            self.logger.warning(f"[yellow]⚠ 最终验证失败[/yellow] [类型] {v_res.type} [摘要] {v_res.summary} [错误] {error_details}")
            self.file_only_logger.warning(f"最终验证失败 [type={v_res.type}] [summary={v_res.summary}] [errors={json.dumps([{'file': err.file, 'line': err.line, 'message': err.message} for err in (v_res.errors or [])], ensure_ascii=False)}]")
        
        if not v_res.ok:
            text = f"最终验证失败：{v_res.summary}\n"
            if v_res.errors:
                for err in v_res.errors[:10]:
                    text += f"- {err.file}:{err.line} {err.message}\n"
            _set_state(AgentState.DONE, {"ok": False})
            return AgentTurn(assistant_text=text, tool_used=tool_used, trace_id=trace_id, events=[])
        return None

    def _execute_react_fallback_loop(
        self,
        trace_id: str,
        keywords: set[str],
        confirm: Callable[[str], bool],
        events: list[dict[str, Any]],
        _ev: Callable[[str, dict[str, Any]], None],
        _llm_chat: Callable[[str, str | None], str],
        _try_parse_tool_call: Callable[[str], dict[str, Any] | None],
        _tool_result_to_message: Callable[[str, ToolResult, set[str] | None], str],
        _set_state: Callable[[AgentState, dict[str, Any] | None], None],
    ) -> AgentTurn:
        """执行 ReAct fallback 循环（单级循环，无规划）。"""
        _set_state(AgentState.EXECUTING, {"mode": "react_fallback"})
        tool_used = False
        
        for iteration in range(20):  # hard stop to avoid infinite loops
            self.logger.info(f"[bold yellow]→ 第 {iteration + 1} 轮：请求 LLM（消息数={len(self.messages)}）[/bold yellow]")
            _ev("llm_request", {"messages": len(self.messages)})
            
            # 记录请求参数到文件（不输出到屏幕）
            self._log_llm_request_params_to_file()
            
            assistant = _llm_chat("react_fallback", None)
            
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
            self._log_llm_response_data_to_file(assistant, tool_call)
            if tool_call is None:
                self.logger.info(
                    "[bold green]✓ LLM 返回最终回复（无工具调用）[/bold green] "
                    f"[轮次] {iteration + 1}/20 [响应长度] {len(assistant)} 字符"
                )
                self.messages.append(ChatMessage(role="assistant", content=assistant))
                self.audit.write(trace_id=trace_id, event="assistant_text", data={"text": assistant})
                _ev("final_text", {"text": assistant[:4000], "truncated": len(assistant) > 4000})
                self._trim_history(max_messages=30)
                return AgentTurn(assistant_text=assistant, tool_used=tool_used, trace_id=trace_id, events=events)

            name = tool_call["tool"]
            args = tool_call["args"]
            args_summary = self._format_args_summary(name, args)
            self.logger.info(
                f"[bold blue]🔧 解析到工具调用: {name}[/bold blue] "
                f"[轮次] {iteration + 1}/20 [参数] {args_summary}"
            )
            self.file_only_logger.info(
                f"工具调用详情 [iteration={iteration + 1}] [tool={name}] [args={json.dumps(args, ensure_ascii=False)}]"
            )
            _ev("tool_call_parsed", {"tool": name, "args": args})

            clean_assistant = json.dumps(tool_call, ensure_ascii=False)
            self.messages.append(ChatMessage(role="assistant", content=clean_assistant))
            _ev("assistant_tool_call_recorded", {"tool": name})
            self._trim_history(max_messages=30)

            # 调用统一生命周期
            result = self._run_tool_lifecycle(name, args, trace_id, confirm, _ev)
            tool_used = True

            _ev("tool_result", {"tool": name, "ok": result.ok, "error": result.error, "payload": result.payload})
            
            # 回喂结果
            result_msg = _tool_result_to_message(name, result, keywords=keywords)
            self.messages.append(ChatMessage(role="user", content=result_msg))
            self.logger.debug(f"[dim]工具结果已回喂[/dim] [工具] {name}")
            self.file_only_logger.debug(f"工具结果回喂 [tool={name}] [len={len(result_msg)}]")
            _ev("tool_result_fed_back", {"tool": name})
            self._trim_history(max_messages=30)

        self.logger.warning("[red]⚠ 达到最大工具调用次数（20），停止以避免死循环[/red]")
        _ev("stop_reason", {"reason": "max_tool_calls_reached", "limit": 20})
        return AgentTurn(
            assistant_text="达到本轮最大工具调用次数（20），已停止以避免死循环。请缩小任务或提供更多约束/入口文件。",
            tool_used=tool_used,
            trace_id=trace_id,
            events=events,
        )

    def _execute_plan_steps(
        self,
        plan: Plan,
        trace_id: str,
        keywords: set[str],
        confirm: Callable[[str], bool],
        events: list[dict[str, Any]],
        _ev: Callable[[str, dict[str, Any]], None],
        _llm_chat: Callable[[str, str | None], str],
        _try_parse_tool_call: Callable[[str], dict[str, Any] | None],
        _tool_result_to_message: Callable[[str, ToolResult, set[str] | None], str],
        _set_state: Callable[[AgentState, dict[str, Any] | None], None],
    ) -> tuple[Plan | None, bool, bool]:
        """
        执行计划的所有步骤（主循环）。
        返回: (plan, tool_used, did_modify_code)
        """
        _set_state(AgentState.EXECUTING, {"steps": len(plan.steps)})
        self.logger.info("[bold magenta]▶ 进入执行阶段：按 Plan 步骤编排[/bold magenta]")

        replans_used = 0
        step_cursor = 0
        tool_used = False
        did_modify_code = False

        while True:
            if plan is None:
                break
            if step_cursor >= len(plan.steps):
                break

            step = plan.steps[step_cursor]

            # 依赖检查
            unmet_deps = self._check_step_dependencies(step, plan, trace_id, _ev)
            if unmet_deps:
                step_cursor += 1
                continue

            step.status = "in_progress"
            self.audit.write(trace_id=trace_id, event="plan_step_start", data={"step_id": step.id, "description": step.description})
            _ev("plan_step_start", {"step_id": step.id, "idx": step_cursor + 1, "total": len(plan.steps)})

            # 每个步骤内部，允许若干次工具调用
            for iteration in range(self.cfg.orchestrator.max_step_tool_calls):
                control_signal, iter_did_modify, iter_did_use_tool = self._execute_single_step_iteration(
                    step, step_cursor, plan, iteration, trace_id, keywords, confirm,
                    _ev, _llm_chat, _try_parse_tool_call, _tool_result_to_message
                )
                
                if iter_did_modify:
                    did_modify_code = True
                if iter_did_use_tool:
                    tool_used = True
                
                if control_signal == "STEP_DONE":
                    break
                elif control_signal == "REPLAN":
                    break

            # 步骤迭代循环结束后强制熔断
            if step.status == "in_progress":
                self.logger.warning(
                    f"[yellow]⚠ 步骤达到最大迭代次数但未完成，强制标记为 failed[/yellow] "
                    f"[步骤] {step.id} [描述] {step.description} "
                    f"[最大迭代] {self.cfg.orchestrator.max_step_tool_calls} [工具使用] {tool_used}"
                )
                self.file_only_logger.warning(
                    f"步骤达到最大迭代次数 [step_id={step.id}] [description={step.description}] "
                    f"[max_iter={self.cfg.orchestrator.max_step_tool_calls}] [tools_used={tool_used}]"
                )
                step.status = "failed"
                self.audit.write(trace_id=trace_id, event="plan_step_max_iter", data={"step_id": step.id, "max_iter": self.cfg.orchestrator.max_step_tool_calls})
                _ev("plan_step_max_iter", {"step_id": step.id, "max_iter": self.cfg.orchestrator.max_step_tool_calls})

            # 步骤结束后，根据状态推进
            if step.status == "done":
                step_cursor += 1
                continue

            # 如果步骤要求重规划
            if step.status == "failed":
                new_plan, new_replans_used = self._handle_replanning(step, plan, replans_used, trace_id, tool_used, _ev, _llm_chat, _set_state)
                if new_plan is None:
                    if replans_used >= self.cfg.orchestrator.max_replans:
                        return None, tool_used, did_modify_code
                    return None, tool_used, did_modify_code
                plan = new_plan
                replans_used = new_replans_used
                step_cursor = 0
                continue

            # 处理 blocked 步骤：检查是否所有步骤都被 blocked（死锁检测）
            if step.status == "blocked":
                all_blocked_or_done = all(s.status in ("blocked", "done") for s in plan.steps)
                if all_blocked_or_done and any(s.status == "blocked" for s in plan.steps):
                    self.logger.error("[red]✗ 检测到依赖死锁：所有未完成步骤都处于 blocked 状态[/red]")
                    _ev("stop_reason", {"reason": "dependency_deadlock"})
                    return None, tool_used, did_modify_code
                step_cursor += 1
                continue

            # 其他状态（卡住/未完成）：熔断
            _ev("stop_reason", {"reason": "step_not_completed", "step_id": step.id})
            return None, tool_used, did_modify_code

        return plan, tool_used, did_modify_code

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

    def _format_args_summary(self, tool_name: str, args: dict[str, Any]) -> str:
        """
        格式化工具参数摘要（用于日志输出）。
        
        根据工具类型提取关键参数，避免输出过长。
        """
        if tool_name == "read_file":
            path = args.get("path", "")
            offset = args.get("offset")
            limit = args.get("limit")
            parts = [f"path={path}"]
            if offset is not None:
                parts.append(f"offset={offset}")
            if limit is not None:
                parts.append(f"limit={limit}")
            return " ".join(parts)
        elif tool_name == "grep":
            pattern = args.get("pattern", "")[:60]
            path = args.get("path", ".")
            return f"pattern={pattern!r} path={path}"
        elif tool_name == "apply_patch":
            path = args.get("path", "")
            expected = args.get("expected_replacements", 1)
            fuzzy = args.get("fuzzy", False)
            return f"path={path} expected={expected} fuzzy={fuzzy}"
        elif tool_name == "write_file":
            path = args.get("path", "")
            text_len = len(args.get("text", ""))
            return f"path={path} text_len={text_len}"
        elif tool_name == "run_cmd":
            cmd = args.get("command", "")[:100]
            cwd = args.get("cwd", ".")
            return f"cmd={cmd!r} cwd={cwd}"
        elif tool_name == "list_dir":
            path = args.get("path", ".")
            return f"path={path}"
        elif tool_name == "glob_file_search":
            pattern = args.get("glob_pattern", "")
            target = args.get("target_directory", ".")
            return f"pattern={pattern} target={target}"
        else:
            # 通用：只显示前 3 个参数，避免过长
            items = list(args.items())[:3]
            parts = [f"{k}={str(v)[:50]}" for k, v in items]
            if len(args) > 3:
                parts.append("...")
            return " ".join(parts)

    def _format_result_summary(self, tool_name: str, result: ToolResult) -> str:
        """
        格式化工具执行结果摘要（用于日志输出）。
        
        根据工具类型和结果提取关键信息，避免输出过长。
        """
        if not result.ok:
            error_msg = result.error.get("message", str(result.error)) if isinstance(result.error, dict) else str(result.error)
            return f"失败: {error_msg[:100]}"
        
        if not result.payload:
            return "成功（无 payload）"
        
        payload = result.payload
        
        if tool_name == "read_file":
            text_len = len(payload.get("text", ""))
            return f"成功: 读取 {text_len} 字符"
        elif tool_name == "grep":
            hits = payload.get("hits", [])
            count = len(hits)
            truncated = payload.get("truncated", False)
            return f"成功: 找到 {count} 个匹配{'（已截断）' if truncated else ''}"
        elif tool_name == "apply_patch":
            replacements = payload.get("replacements", 0)
            undo_id = payload.get("undo_id", "")
            return f"成功: {replacements} 处替换 undo_id={undo_id[:20]}"
        elif tool_name == "write_file":
            return "成功: 文件已写入"
        elif tool_name == "run_cmd":
            exit_code = payload.get("exit_code", -1)
            stdout_len = len(payload.get("stdout", ""))
            stderr_len = len(payload.get("stderr", ""))
            return f"成功: exit_code={exit_code} stdout={stdout_len}字符 stderr={stderr_len}字符"
        elif tool_name == "list_dir":
            items = payload.get("items", [])
            count = len(items)
            return f"成功: {count} 项"
        elif tool_name == "glob_file_search":
            matches = payload.get("matches", [])
            count = len(matches)
            return f"成功: 找到 {count} 个文件"
        elif tool_name == "search_semantic":
            hits = payload.get("hits", [])
            count = len(hits)
            return f"成功: {count} 个语义匹配"
        else:
            # 通用：显示 payload 的键
            keys = list(payload.keys())[:3]
            return f"成功: {', '.join(keys)}{'...' if len(payload) > 3 else ''}"

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


