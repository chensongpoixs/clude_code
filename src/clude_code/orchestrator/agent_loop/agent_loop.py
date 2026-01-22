import json
import re
import uuid
from pathlib import Path
from typing import Any, Callable, List, Dict, Optional

from clude_code.config.config import CludeConfig
from clude_code.llm.llama_cpp_http import ChatMessage, LlamaCppHttpClient
from clude_code.observability.audit import AuditLogger
from clude_code.observability.trace import TraceLogger
from clude_code.observability.usage import SessionUsage
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
from clude_code.orchestrator.registry import IntentRegistry, IntentRouter
from clude_code.orchestrator.registry.prompt_profiles import PromptProfileRegistry
from clude_code.orchestrator.approvals import ApprovalStore
from clude_code.orchestrator.risk_assessor import assess_plan_risk, merge_intent_and_plan_risk
from clude_code.orchestrator.sandbox import SandboxRunner
from clude_code.orchestrator.sandbox.merge import merge_modified_files
from clude_code.core.project_paths import resolve_path_template, DEFAULT_PROJECT_ID

from .models import AgentTurn
from .parsing import try_parse_tool_call
from .prompts import load_project_memory
from clude_code.prompts import read_prompt, render_prompt, PromptManager
from .tool_lifecycle import run_tool_lifecycle
from .planning import execute_planning_phase
from .execution import (
    check_step_dependencies as _exec_check_step_dependencies,
    handle_tool_call_in_step as _exec_handle_tool_call_in_step,
    execute_single_step_iteration as _exec_execute_single_step_iteration,
    handle_replanning as _exec_handle_replanning,
    execute_final_verification as _exec_execute_final_verification,
    execute_plan_steps as _exec_execute_plan_steps,
)
from .llm_io import (
    llm_chat as _io_llm_chat,
    log_llm_request_params_to_file as _io_log_llm_request_params_to_file,
    log_llm_response_data_to_file as _io_log_llm_response_data_to_file,
    normalize_messages_for_llama as _io_normalize_messages_for_llama,
)
from .react import execute_react_fallback_loop as _react_execute_react_fallback_loop
from .semantic_search import semantic_search as _semantic_search_fn
from .tool_dispatch import dispatch_tool as _dispatch_tool_fn, iter_tool_specs as _iter_tool_specs


def _try_parse_tool_call(text: str) -> dict[str, Any] | None:
    """
    兼容层：旧函数名 `_try_parse_tool_call`。
    # 新实现已迁移到 `agent_loop/parsing.py`，保留此入口避免大范围改动。
    #
    # 使用示例：
    # ```python
    # text = "Call tool: read_file path=./file.txt"
    # result = _try_parse_tool_call(text)
    # print(result)
    # ```
    """
    obj = try_parse_tool_call(text)
    if obj is None:
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
    
    def __init__(self, cfg: CludeConfig, *, session_id: str | None = None, project_id: str | None = None) -> None:
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
            session_id: 会话 ID（用于 trace/audit 关联）
            project_id: 项目 ID（用于多项目隔离，默认 "default"）
        
        流程图: 见 `agent_loop_init_flow.svg`
        """
        self.cfg = cfg
        self.project_id = project_id or "default"
        self.logger = get_logger(
            __name__,
            workspace_root=cfg.workspace_root,
            log_to_console=cfg.logging.log_to_console,
            level=cfg.logging.level,
            log_format=cfg.logging.log_format,
            date_format=cfg.logging.date_format,
            project_id=self.project_id,
        )
        # 创建只写入文件的 logger（用于记录 LLM 请求/响应详情）
        effective_log_file = resolve_path_template(
            cfg.logging.file_path,
            workspace_root=cfg.workspace_root,
            project_id=self.project_id,
        )
        self.file_only_logger = get_logger(
            f"{__name__}.llm_detail",
            workspace_root=cfg.workspace_root,
            log_to_console=False,  # 只写入文件，不输出到控制台
            level=cfg.logging.level,
            log_file=effective_log_file,
            max_bytes=cfg.logging.max_bytes,
            backup_count=cfg.logging.backup_count,
            log_format=cfg.logging.log_format,
            date_format=cfg.logging.date_format,
            project_id=self.project_id,
        )
        # 会话 ID：用于 trace/audit 关联。支持从 CLI 恢复会话时复用旧 session_id
        self.session_id = session_id or f"sess_{id(self)}"
        self.logger.info(f"[dim]初始化 AgentLoop，session_id={self.session_id}[/dim]")
        self.llm = LlamaCppHttpClient(
            base_url=cfg.llm.base_url,
            api_mode=cfg.llm.api_mode,  # type: ignore[arg-type]
            model=cfg.llm.model,
            temperature=cfg.llm.temperature,
            max_tokens=cfg.llm.max_tokens,
            timeout_s=cfg.llm.timeout_s,
            api_key=cfg.llm.api_key,  # 支持 OpenAI/Azure 等需要认证的 API
        )
        self.tools = LocalTools(
            cfg.workspace_root,
            max_file_read_bytes=cfg.limits.max_file_read_bytes,
            max_output_bytes=cfg.limits.max_output_bytes,
            project_id=self.project_id,
        )
        
        # 初始化工具配置（统一管理，从全局配置注入）
        try:
            from clude_code.config import set_tool_configs
            set_tool_configs(cfg)
            # 初始化天气工具配置（向后兼容）
            from clude_code.tooling.tools.weather import set_weather_config
            set_weather_config(cfg)
        except ImportError:
            pass  # 工具模块可选
        
        self.audit = AuditLogger(cfg.workspace_root, self.session_id, project_id=self.project_id, security=cfg.audit_security)
        self.trace = TraceLogger(cfg.workspace_root, self.session_id, project_id=self.project_id)
        self.usage = SessionUsage()
        
        # Knowledge / RAG systems
        self.indexer = IndexerService(cfg)
        self.indexer.start()  # Start background indexing (best-effort)
        if str(getattr(self.indexer, "status", "")).startswith("disabled:"):
            self.logger.info(f"[dim]后台索引已禁用: {self.indexer.status}[/dim]")
        else:
            self.logger.info("[dim]启动后台索引服务（LanceDB RAG）[/dim]")
        self.embedder = CodeEmbedder(cfg)
        self.vector_store = VectorStore(cfg, project_id=self.project_id)
        self.verifier = Verifier(cfg)
        self.classifier = IntentClassifier(self.llm, file_only_logger=self.file_only_logger)
        # Intent Registry（优先使用 registry，fallback 到 LLM classifier）
        self.intent_registry = IntentRegistry(cfg.workspace_root)
        # Prompt Profile Registry（中间层：Intent -> Profile -> Prompts）
        self.prompt_profiles = PromptProfileRegistry(cfg.workspace_root)
        def _fallback_intent_classifier(text: str) -> tuple[str, float]:
            # registry stage=intent_classify（可运营版本切换）
            prompt = self._compose_stage_prompt(stage="intent_classify", vars={"user_text": text}) or render_prompt("user/stage/intent_classify.j2", user_text=text)
            result = self.classifier.classify_with_prompt(prompt, user_text_for_log=text)
            return result.category.value, float(result.confidence)

        self.intent_router = IntentRouter(
            self.intent_registry,
            fallback_classifier=_fallback_intent_classifier,
        )
        self._current_intent_match = None
        self.prompt_manager = PromptManager(workspace_root=cfg.workspace_root)
        self.approvals = ApprovalStore(workspace_root=cfg.workspace_root, project_id=self.project_id)
        self.sandbox = SandboxRunner(cfg.workspace_root)

        # Phase 2：可选企业策略引擎（默认关闭，避免改变现有行为）
        self.enterprise_policy_engine = None
        try:
            if bool(getattr(cfg.policy, "enterprise_enabled", False)):
                from clude_code.policy.enterprise_policy import PolicyEngine
                from pathlib import Path as _Path

                url = str(getattr(cfg.policy, "enterprise_policy_server_url", "") or "").strip() or None
                ttl = int(getattr(cfg.policy, "enterprise_policy_cache_ttl_s", 3600) or 3600)
                engine = PolicyEngine(_Path(cfg.workspace_root), policy_server_url=url, cache_ttl_s=ttl)
                uid = str(getattr(cfg.policy, "enterprise_user_id", "default") or "default")
                engine.set_current_user(uid)
                self.enterprise_policy_engine = engine
        except Exception as e:
            # 策略引擎初始化失败不阻塞主流程
            self.file_only_logger.warning(f"enterprise policy engine init failed: {e}", exc_info=True)

        # 阶段 C: 追踪本轮修改过的文件路径，用于选择性测试
        self._turn_modified_paths: set[Path] = set()

        # display 工具需要的运行时上下文（在 run_turn 中设置）
        self._current_ev: Callable[[str, dict[str, Any]], None] | None = None
        self._current_trace_id: str | None = None

        # Initialize with Repo Map for better global context (Aider-style)
        import platform
        repo_map = self.tools.generate_repo_map()
        env_info = f"操作系统: {platform.system()} ({platform.release()})\n当前绝对路径: {self.cfg.workspace_root}"

        # Claude Code 对标：自动加载 CLUDE.md 作为项目记忆（只读、失败不阻塞）
        project_memory_text, project_memory_meta = load_project_memory(self.cfg.workspace_root)
        self._project_memory_meta: dict[str, object] = project_memory_meta
        self._project_memory_emitted: bool = False

        # 缓存 system prompt 动态变量，便于每轮根据 intent/profile 刷新 system prompt
        self._system_project_memory_text = project_memory_text
        self._system_env_info = env_info
        self._system_repo_map = repo_map

        combined_system_prompt = self._build_system_prompt(
            project_memory_text=project_memory_text,
            env_info=env_info,
            repo_map=repo_map,
        )
        
        self.messages: list[ChatMessage] = [
            ChatMessage(role="system", content=combined_system_prompt),
        ]
        if bool(project_memory_meta.get("loaded")):
            self.logger.info(f"[dim]已加载 CLUDE.md 项目记忆: {project_memory_meta}[/dim]")
        else:
            self.logger.info("[dim]未加载 CLUDE.md（未找到或为空）[/dim]")
        self.logger.info("[dim]初始化系统提示词（包含 Repo Map/环境信息/可选项目记忆）[/dim]")

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
        # 阶段 C: Trace ID 必须跨进程稳定且全局唯一
        trace_id = f"trace_{uuid.uuid4().hex}"
        self.logger.info(f"[bold cyan]开始新的一轮对话[/bold cyan] trace_id={trace_id}")
        self.logger.info(f"[dim]用户输入: {user_text[:100]}{'...' if len(user_text) > 100 else ''}[/dim]")

        # 阶段 C: 清空本轮修改追踪
        self._turn_modified_paths.clear()
        # LLM 请求/返回日志：本轮只打印"本轮新增 user + 本次返回"，不输出历史轮次
        # 说明：llm_io.py 会用这个 cursor 计算"本次请求新增消息"的切片范围
        self._llm_log_cursor = len(self.messages)

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
                    # 透传 trace_id：live UI / TUI / bug report 需要对齐同一轮 turn 的可追溯标识
                    on_event({**e, "trace_id": trace_id})
                except Exception as ex:
                    self.file_only_logger.warning(f"on_event 回调异常: {ex}", exc_info=True)

        # 让 live UI/TUI 能展示"默认 chat 日志"的开场行
        _ev("turn_start", {"trace_id": trace_id})

        # 提取关键词并上报（用于 UI 显示"分词"）—— 必须在 _ev 定义之后调用
        keywords = self._extract_keywords(user_text)
        _ev("keywords_extracted", {"keywords": list(keywords)})


        # 设置运行时上下文，供 display 工具使用
        self._current_ev = _ev
        self._current_trace_id = trace_id

        # 仅在本会话首次 turn 发出“项目记忆加载状态”事件，供 live UI 展示
        if not getattr(self, "_project_memory_emitted", False):
            try:
                _ev("project_memory", dict(getattr(self, "_project_memory_meta", {}) or {}))
            finally:
                self._project_memory_emitted = True

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
        planning_prompt = self._build_planning_prompt(user_text) if enable_planning else None

        # Prompt Profile：根据当前 intent/profile 刷新 system prompt（让本轮立即生效）
        self._refresh_system_prompt_for_current_intent(_ev)

        # 2) 记录用户输入（必要时把规划提示并入同一条 user 消息，避免 role 不交替）
        self.audit.write(trace_id=trace_id, event="user_message", data={"text": user_text})
        _ev("user_message", {"text": user_text})
        # User Prompt：禁止直接使用 raw user_text 作为最终 user prompt，必须经模板结构化
        match = getattr(self, "_current_intent_match", None)
        intent_name = str(getattr(match, "name", "") or "default")
        risk_level = str(getattr(getattr(match, "risk_level", None), "value", "") or getattr(match, "risk_level", "") or "MEDIUM")
        user_content = self._compose_stage_prompt(
            stage="user_prompt",
            vars={
                "planning_prompt": (planning_prompt or ""),
                "project_id": str(self.project_id or DEFAULT_PROJECT_ID),
                "intent_name": intent_name,
                "risk_level": str(risk_level),
                "user_text": user_text,
            },
        )
        if not user_content:
            # 兜底：保持旧行为（避免模板缺失导致空 prompt）
            user_content = user_text if planning_prompt is None else planning_prompt

        self.logger.info(f"[bold cyan]发送给 LLM 的 user_content[/bold cyan] len={len(user_content)}")
        # 透传 user_content（用于“对话/输出”窗格复刻 chat 默认日志）
        _ev(
            "user_content_built",
            {
                "preview": user_content[:2000],
                "truncated": len(user_content) > 2000,
                "messages_count": len(self.messages) + 1,  # 即将 append
                "planning_prompt_included": bool(planning_prompt),
            },
        )
        self.messages.append(ChatMessage(role="user", content=user_content))
        self._trim_history(max_messages=30)
        self.logger.debug(f"[dim]当前消息历史长度: {len(self.messages)}[/dim]")

        llm_chat = (lambda stage, step_id=None: self._llm_chat(stage, step_id=step_id, _ev=_ev))

        # 3) 规划阶段
        plan: Plan | None = None
        if enable_planning:
            _set_state(AgentState.PLANNING, {"reason": "enable_planning"})
            plan = self._execute_planning_phase(user_text, planning_prompt, trace_id, _ev, llm_chat)

        # Phase 2：审批门（强验收增强版：intent_risk 与 plan_risk 取最大值）
        if plan is not None and enable_planning:
            match = getattr(self, "_current_intent_match", None)
            intent_risk_s = str(getattr(match, "risk_level", "") or "MEDIUM").upper()
            try:
                from clude_code.orchestrator.registry.schema import RiskLevel as _RiskLevel

                intent_risk = _RiskLevel(intent_risk_s) if intent_risk_s in {"LOW", "MEDIUM", "HIGH", "CRITICAL"} else _RiskLevel.MEDIUM
            except Exception:
                intent_risk = None

            plan_assess = assess_plan_risk(plan)
            plan_risk = plan_assess.risk_level
            final_risk = plan_risk if intent_risk is None else merge_intent_and_plan_risk(intent_risk, plan_risk)
            risk = str(final_risk.value if hasattr(final_risk, "value") else str(final_risk)).upper()

            if risk in {"HIGH", "CRITICAL"}:
                try:
                    try:
                        plan_md = render_plan_markdown(plan)
                    except Exception:
                        plan_md = f"{plan.title} (steps={len(plan.steps)})"
                    if len(plan_md) > 2000:
                        plan_md = plan_md[:1999] + "…"

                    req = self.approvals.create(
                        trace_id=trace_id,
                        intent_name=(match.name if match else "default"),
                        risk_level=risk,
                        plan_summary=plan_md,
                        plan=plan.model_dump(mode="json"),
                    )
                    self.audit.write(trace_id=trace_id, event="approval_required", data=req.model_dump())
                    _ev("approval_required", req.model_dump())
                    _set_state(
                        AgentState.WAITING_FOR_APPROVAL,
                        {
                            "approval_id": req.id,
                            "risk_level": risk,
                            "plan_risk": str(plan_risk.value if hasattr(plan_risk, "value") else str(plan_risk)),
                            "plan_risk_reason": plan_assess.reason,
                        },
                    )

                    # MVP：confirm 视为本地审批（仍落盘+审计）
                    if confirm(f"检测到高风险任务({risk})，需要审批才能继续。是否批准？approval_id={req.id}"):
                        decided = self.approvals.approve(req.id, decided_by="local_confirm")
                        if not decided:
                            return AgentTurn(
                                assistant_text=f"审批写入失败，已阻塞执行。approval_id={req.id}",
                                tool_used=False,
                                trace_id=trace_id,
                                events=events,
                            )
                        self.audit.write(trace_id=trace_id, event="approval_approved", data=decided.model_dump())
                        _ev("approval_status_changed", decided.model_dump())
                    else:
                        # 强验收增强：用户不批准时保持 pending（允许后续 CLI approve）
                        self.audit.write(trace_id=trace_id, event="approval_pending", data={"approval_id": req.id, "risk_level": risk})
                        _ev("approval_status_changed", {"id": req.id, "status": "pending", "risk_level": risk})
                        return AgentTurn(
                            assistant_text=(
                                f"已进入等待审批状态（风险={risk}）。approval_id={req.id}\n"
                                f"可用命令批准/拒绝：`clude approvals approve {req.id}` 或 `clude approvals reject {req.id}`\n"
                                f"批准后继续执行：`clude approvals run {req.id} --yes`（或不加 --yes 进行交互确认）"
                            ),
                            tool_used=False,
                            trace_id=trace_id,
                            events=events,
                        )
                except Exception as e:
                    self.file_only_logger.warning(f"approval gate failed: {e}", exc_info=True)
                    return AgentTurn(
                        assistant_text=f"审批门处理失败，已阻塞执行以保证安全。错误={type(e).__name__}: {e}",
                        tool_used=False,
                        trace_id=trace_id,
                        events=events,
                    )

        # 4) 执行阶段
        if plan is not None:
            # Phase 3：CRITICAL 默认沙箱执行（MVP：copy/worktree 执行 + 通过验证后合并修改文件）
            match = getattr(self, "_current_intent_match", None)
            # 使用 final_risk（intent_risk 与 plan_risk 取最大值），避免仅凭 intent 配置漏沙箱
            intent_risk_s = str(getattr(match, "risk_level", "") or "MEDIUM").upper()
            try:
                from clude_code.orchestrator.registry.schema import RiskLevel as _RiskLevel

                intent_risk = _RiskLevel(intent_risk_s) if intent_risk_s in {"LOW", "MEDIUM", "HIGH", "CRITICAL"} else _RiskLevel.MEDIUM
            except Exception:
                intent_risk = None

            plan_assess2 = assess_plan_risk(plan)
            plan_risk2 = plan_assess2.risk_level
            final_risk2 = plan_risk2 if intent_risk is None else merge_intent_and_plan_risk(intent_risk, plan_risk2)
            risk_now = str(final_risk2.value if hasattr(final_risk2, "value") else str(final_risk2)).upper()

            if risk_now == "CRITICAL":
                ctx = self.sandbox.create(prefer="worktree")
                self.audit.write(trace_id=trace_id, event="sandbox_created", data={"id": ctx.sandbox_id, "kind": ctx.kind, "path": str(ctx.sandbox_root)})
                _ev("sandbox_created", {"id": ctx.sandbox_id, "kind": ctx.kind, "path": str(ctx.sandbox_root)})
                try:
                    # 在沙箱中跑一个新的 AgentLoop（同一 config，但 workspace_root 指向沙箱目录）
                    from copy import deepcopy
                    sb_cfg = deepcopy(self.cfg)
                    sb_cfg.workspace_root = str(ctx.sandbox_root)
                    sb_loop = AgentLoop(sb_cfg, session_id=self.session_id, project_id=self.project_id)

                    # 把当前 plan 执行到沙箱
                    sb_plan, tool_used, did_modify_code = sb_loop._execute_plan_steps(
                        plan,
                        trace_id,
                        keywords,
                        confirm,
                        events,
                        _ev,
                        (lambda stage, step_id=None: sb_loop._llm_chat(stage, step_id=step_id, _ev=_ev)),
                        _try_parse_tool_call,
                        _tool_result_to_message,
                        _set_state,
                    )
                    if sb_plan is None:
                        return AgentTurn(assistant_text="沙箱执行失败，已回滚（未污染主 workspace）。", tool_used=tool_used, trace_id=trace_id, events=events)

                    # 沙箱验证
                    v_res = sb_loop.verifier.run_verify(modified_paths=list(sb_loop._turn_modified_paths))
                    if not v_res.ok:
                        self.audit.write(trace_id=trace_id, event="sandbox_discarded", data={"id": ctx.sandbox_id, "reason": "verify_failed", "summary": v_res.summary})
                        self.sandbox.discard(ctx)
                        return AgentTurn(assistant_text=f"沙箱验证失败，已回滚：{v_res.summary}", tool_used=tool_used, trace_id=trace_id, events=events)

                    # 合并：把沙箱中的修改文件映射回主 workspace，然后复制覆盖
                    ws_root = Path(self.cfg.workspace_root).resolve()
                    sb_root = Path(sb_cfg.workspace_root).resolve()
                    modified_in_ws: list[Path] = []
                    for p in list(sb_loop._turn_modified_paths):
                        try:
                            rel = p.resolve().relative_to(sb_root)
                        except Exception:
                            continue
                        modified_in_ws.append((ws_root / rel).resolve())

                    merge = merge_modified_files(
                        sandbox_root=ctx.sandbox_root,
                        workspace_root=ws_root,
                        modified_abs_paths_in_workspace=modified_in_ws,
                    )
                    if not merge.ok:
                        self.audit.write(trace_id=trace_id, event="sandbox_discarded", data={"id": ctx.sandbox_id, "reason": "merge_failed", "error": merge.error})
                        self.sandbox.discard(ctx)
                        return AgentTurn(assistant_text=f"沙箱合并失败，已回滚：{merge.error}", tool_used=tool_used, trace_id=trace_id, events=events)

                    self.audit.write(trace_id=trace_id, event="sandbox_merge_applied", data={"id": ctx.sandbox_id, "files": merge.copied_files})
                    _ev("sandbox_merge_applied", {"id": ctx.sandbox_id, "files": merge.copied_files})
                    # 同步本轮修改路径（用于 verify/报告）
                    self._turn_modified_paths |= set(modified_in_ws)
                    self.sandbox.discard(ctx)
                    plan = sb_plan
                except Exception as e:
                    self.audit.write(trace_id=trace_id, event="sandbox_discarded", data={"id": ctx.sandbox_id, "reason": "exception", "error": str(e)})
                    self.sandbox.discard(ctx)
                    return AgentTurn(assistant_text=f"沙箱执行异常，已回滚：{type(e).__name__}: {e}", tool_used=False, trace_id=trace_id, events=events)
            else:
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
        assistant_text = self._execute_react_fallback_loop(
            trace_id=trace_id,
            keywords=keywords,
            confirm=confirm,
            events=events,
            _ev=_ev,
            _llm_chat=llm_chat,
            _try_parse_tool_call=_try_parse_tool_call,
            _tool_result_to_message=_tool_result_to_message,
            _set_state=_set_state,
        ).assistant_text # 获取 fallback 循环的最终文本

        # LLM 空白响应的智能处理：如果 LLM 返回空白，返回一个预设的友好提示
        cleaned_text = assistant_text.strip()
        if not cleaned_text or len(re.sub(r'\s+', '', cleaned_text)) < 5: # 移除所有空白字符后少于5个有效字符
            self.logger.warning(f"[yellow]LLM 返回空白或过短的有效内容，将使用预设回复。[/yellow] trace_id={trace_id}")
            assistant_text = "你好！有什么我可以帮你做的吗？"
            tool_used = False # 避免将预设回复标记为工具使用
        else:
            tool_used = False # 在 ReAct fallback 之外，assistant_text 不代表工具使用

        # 5) 记录 LLM 最终响应
        self.audit.write(trace_id=trace_id, event="assistant_text", data={"text": assistant_text})
        _ev("assistant_text", {"text": assistant_text})
        self.messages.append(ChatMessage(role="assistant", content=assistant_text))
        self._trim_history(max_messages=30)

        return AgentTurn(
            assistant_text=assistant_text,
            tool_used=tool_used,
            trace_id=trace_id,
            events=events,
        )

    def _extract_keywords(self, user_text: str) -> set[str]:
        """提取用户输入中的关键词（用于语义窗口采样）。"""
        keywords = set(re.findall(r'\w{4,}', user_text.lower()))
        keywords -= {"please", "help", "find", "where", "change", "file", "code", "repo", "make"}
        if keywords:
            self.logger.debug(f"[dim]提取关键词: {keywords}[/dim]")
        return keywords

    def _normalize_messages_for_llama(self, stage: str, *, step_id: str | None = None, _ev: Callable[[str, dict[str, Any]], None] | None = None) -> None:
        return _io_normalize_messages_for_llama(self, stage, step_id=step_id, _ev=_ev)

    def _llm_chat(self, stage: str, *, step_id: str | None = None, _ev: Callable[[str, dict[str, Any]], None] | None = None) -> str:
        return _io_llm_chat(self, stage, step_id=step_id, _ev=_ev)

    """
    获取可用于 prompt 的工具名列表（Prompt Tool Names）
    @author chensong（chensong）
    @date 2026-01-20
    @brief 从 ToolSpec 注册表提取“可见且可调用”的工具名，用于 planning prompt 的 tools_expected 提示
    """
    def _get_prompt_tool_names(self) -> list[str]:
        # 说明：
        # - 统一以 tool_dispatch.iter_tool_specs() 为单一事实来源（避免手写漏工具）
        # - 仅收集 visible_in_prompt 且 callable_by_model 的工具
        # - 做去重 + 稳定顺序（保持注册表顺序）
        try:
            names = [
                s.name
                for s in _iter_tool_specs()
                if getattr(s, "visible_in_prompt", True) and getattr(s, "callable_by_model", True)
            ]
        except Exception:
            # 兜底：如果 registry 异常，避免 planning 阶段崩溃
            names = ["read_file", "grep", "apply_patch"]

        seen: set[str] = set()
        out: list[str] = []
        for n in names:
            if not n or not isinstance(n, str):
                continue
            if n in seen:
                continue
            seen.add(n)
            out.append(n)
        return out

    """
    构建规划阶段提示词（Planning Prompt Builder）
    @author chensong（chensong）
    @date 2026-01-20
    @brief 生成 planning 阶段的 JSON 规划提示，并将 tools_expected 示例自动覆盖所有现有工具
    
    注意（Notes）：
    - 这里返回的是“提示词文本”，不是消息对象；`run_turn` 会把它拼到用户输入后面作为同一条 user 消息发送。
    - tools_expected 的示例必须包含当前工程的全部工具名（从注册表提取，避免漏项）。
    """
    def _build_planning_prompt(self, input_text: str) -> str:
        """
        Phase1（新提示词工程，非兼容旧目录）：
        - 使用 PromptManager（base/domains/tasks 三层继承 + SemVer + 回滚指针）。
        - 不再回退到旧的 `prompts/agent_loop/*` 提示词。
        """
        tool_names = self._get_prompt_tool_names()
        tools_expected_example = json.dumps(tool_names, ensure_ascii=False)
        tools_expected_hint = ", ".join(tool_names)

        match = getattr(self, "_current_intent_match", None)
        prompt_text = self._compose_stage_prompt(
            stage="planning",
            vars={
                "max_plan_steps": int(self.cfg.orchestrator.max_plan_steps),
                "tools_expected_example": tools_expected_example,
                "tools_expected_hint": tools_expected_hint,
                "input_text": input_text,
                "project_id": self.project_id,
                "intent_name": (match.name if match else "default"),
            },
        )
        if not prompt_text:
            # 非兼容模式下的兜底：避免 planning 阶段崩溃（不依赖旧 prompt 文件）
            return (
                "你是任务规划专家，只输出严格 JSON（FullPlan）。\n"
                f"步骤数<= {int(self.cfg.orchestrator.max_plan_steps)}。\n"
                f"可用工具：[{tools_expected_hint}]\n"
                f"目标：{input_text}\n"
            )
        return prompt_text
    # 默认提示词配置，用于 fallback 兜底  
    # 说明：
    # - 统一以 base/domains/tasks 三层继承 + SemVer + 回滚指针。
    # - 不再回退到旧的 `prompts/agent_loop/*` 提示词。
    # - 使用 `prompt_manager` 三层渲染，确保版本化 + 回滚指针。
    # - 避免直接拼接 `SYSTEM_PROMPT`，保持 prompt 结构清晰。 
    # - system :注释作用：用于生成  系统提示词
    # - planning :注释作用：用于生成  规划提示词 
    # - execute_step :注释作用：用于生成  执行步骤提示词
    # - replan :注释作用：用于生成  重规划提示词
    # - plan_patch_retry :注释作用：用于生成  计划补丁重试提示词
    # - plan_parse_retry :注释作用：用于生成  计划解析重试提示词
    # - invalid_step_output_retry :注释作用：用于生成  无效步骤输出重试提示词
    # - intent_classify :注释作用：用于生成  意图分类提示词
    def _default_stage_prompts(self) -> dict[str, dict[str, str]]:

        return {
            # 目录结构对齐 agent_design_v_1.0.md：system/* + user/*
            "system": {"base": "system/core/global.md", "domain": "system/role/developer.md", "task": "system/context/runtime.j2"},
            "user_prompt": {"base": "", "domain": "", "task": "user/intent/meta/query.j2"},
            "planning": {"base": "", "domain": "", "task": "user/stage/planning.j2"},
            "execute_step": {"base": "", "domain": "", "task": "user/stage/execute_step.j2"},
            "replan": {"base": "", "domain": "", "task": "user/stage/replan.j2"},
            "plan_patch_retry": {"base": "", "domain": "", "task": "user/stage/plan_patch_retry.j2"},
            "plan_parse_retry": {"base": "", "domain": "", "task": "user/stage/plan_parse_retry.md"},
            "invalid_step_output_retry": {"base": "", "domain": "", "task": "user/stage/invalid_step_output_retry.md"},
            "intent_classify": {"base": "", "domain": "", "task": "user/stage/intent_classify.j2"},
        }

    def _resolve_stage_prompt_triplet(self, stage: str) -> tuple[str | None, str | None, str | None, str | None, str | None, str | None]:
        cfg0 = self.intent_registry.get_config()
        match = getattr(self, "_current_intent_match", None)
        defaults = self._default_stage_prompts().get(stage, {})

        def _get_stage(cfg_obj):
            try:
                # 兼容两种输入：
                # - ProjectConfig/IntentSpec：有 .prompts
                # - PromptProfileSpec.prompts：本身就是 StagePrompts（直接有 .system/.user_prompt/...）
                if cfg_obj is None:
                    return None
                direct = getattr(cfg_obj, stage, None)
                if direct is not None:
                    return direct
                return getattr(getattr(cfg_obj, "prompts", None), stage, None)
            except Exception:
                return None

        project_stage = _get_stage(cfg0)
        intent_stage = _get_stage(getattr(match, "intent", None)) if match else None

        # Prompt Profile：Intent 通过 prompt_profile 间接选择 prompts
        profile_stage = None
        try:
            profile_name = str(getattr(getattr(match, "intent", None), "prompt_profile", "") or "").strip() if match else ""
            if profile_name:
                prof = self.prompt_profiles.get_profile(profile_name)
                profile_stage = _get_stage(getattr(prof, "prompts", None)) if prof else None
            else:
                # 若 intent 未指定 profile：按分类器五类意图选择默认 profile（可选；profile 不存在则忽略）
                cat = str(getattr(self, "_last_intent_category", "") or "").strip().upper()
                cat_to_profile = {
                    "CODING_TASK": "classifier_coding_task",
                    "ERROR_DIAGNOSIS": "classifier_error_diagnosis",
                    "REPO_ANALYSIS": "classifier_repo_analysis",
                    "DOCUMENTATION_TASK": "classifier_documentation_task",
                    "TECHNICAL_CONSULTING": "classifier_technical_consulting",
                    "PROJECT_DESIGN": "classifier_project_design",
                    "SECURITY_CONSULTING": "classifier_security_consulting",
                    "CAPABILITY_QUERY": "classifier_capability_query",
                    "GENERAL_CHAT": "classifier_general_chat",
                    "CASUAL_CHAT": "classifier_casual_chat",
                    "UNCERTAIN": "classifier_uncertain",
                }
                fallback_profile = cat_to_profile.get(cat)
                if fallback_profile:
                    prof = self.prompt_profiles.get_profile(fallback_profile)
                    profile_stage = _get_stage(getattr(prof, "prompts", None)) if prof else None
        except Exception:
            profile_stage = None

        def _pick(layer: str) -> tuple[str | None, str | None]:
            for s in (intent_stage, profile_stage, project_stage):
                if s is None:
                    continue
                try:
                    l = getattr(s, layer, None)
                    if l and getattr(l, "ref", None):
                        return str(getattr(l, "ref")).strip(), (str(getattr(l, "version")).strip() if getattr(l, "version", None) else None)
                except Exception:
                    continue
            ref = str(defaults.get(layer, "") or "").strip() or None
            return ref, None

        base_ref, base_ver = _pick("base")
        domain_ref, domain_ver = _pick("domain")
        task_ref, task_ver = _pick("task")
        return base_ref, domain_ref, task_ref, base_ver, domain_ver, task_ver

    def _compose_stage_prompt(self, *, stage: str, vars: dict[str, object]) -> str:
        base_ref, domain_ref, task_ref, base_ver, domain_ver, task_ver = self._resolve_stage_prompt_triplet(stage)
        text, _meta = self.prompt_manager.compose(
            base_ref=base_ref,
            domain_ref=domain_ref,
            task_ref=task_ref,
            base_version=base_ver,
            domain_version=domain_ver,
            task_version=task_ver,
            vars=vars,
        )
        return (text or "").strip()

    def _build_system_prompt(self, *, project_memory_text: str, env_info: str, repo_map: str) -> str:
        from .tool_dispatch import render_tools_for_system_prompt

        tools_section = render_tools_for_system_prompt(include_schema=False)
        sys_text = self._compose_stage_prompt(
            stage="system",
            vars={
                "tools_section": tools_section,
                "project_memory": project_memory_text,
                "env_info": f"\n\n=== 环境信息 ===\n{env_info}\n\n=== 代码仓库符号概览 ===\n{repo_map}",
            },
        )
        return sys_text or (tools_section + project_memory_text + "\n" + env_info + "\n" + repo_map)

    def _refresh_system_prompt_for_current_intent(self, _ev: Callable[[str, dict[str, Any]], None]) -> None:
        """每轮根据当前 intent/profile 刷新 system prompt（更新 messages[0]）。"""
        try:
            new_sys = self._build_system_prompt(
                project_memory_text=str(getattr(self, "_system_project_memory_text", "") or ""),
                env_info=str(getattr(self, "_system_env_info", "") or ""),
                repo_map=str(getattr(self, "_system_repo_map", "") or ""),
            )
            if self.messages and self.messages[0].role == "system":
                self.messages[0] = ChatMessage(role="system", content=new_sys)
                _ev("system_prompt_refreshed", {"len": len(new_sys)})
        except Exception as e:
            self.file_only_logger.warning(f"refresh system prompt failed: {e}", exc_info=True)

    def _log_llm_request_params_to_file(self) -> None:
        return _io_log_llm_request_params_to_file(self)

    def _log_llm_response_data_to_file(self, assistant_text: str, tool_call: dict[str, Any] | None) -> None:
        return _io_log_llm_response_data_to_file(self, assistant_text, tool_call)

    def _run_tool_lifecycle(
        self,
        name: str,
        args: dict[str, Any],
        trace_id: str,
        confirm: Callable[[str], bool],
        _ev: Callable[[str, dict[str, Any]], None],
    ) -> ToolResult:
        # 工具白名单约束（来自 Intent Registry）
        match = getattr(self, "_current_intent_match", None)
        if match and getattr(match, "tools", None):
            allowed = set(match.tools)
            if name not in allowed:
                self.logger.warning(f"[yellow]工具被意图限制拦截: {name} (allowed={sorted(allowed)})[/yellow]")
                return ToolResult(
                    ok=False,
                    error={
                        "code": "E_TOOL_NOT_ALLOWED",
                        "message": f"tool '{name}' is not allowed by intent '{match.name}'",
                        "allowed_tools": sorted(allowed),
                        "intent": match.name,
                    },
                )
        return run_tool_lifecycle(self, name, args, trace_id, confirm, _ev)

    def _classify_intent_and_decide_planning(self, user_text: str, _ev: Callable[[str, dict[str, Any]], None]) -> bool:
        """意图分类和决策门：根据用户意图决定是否启用规划。"""
        prompt = self._compose_stage_prompt(stage="intent_classify", vars={"user_text": user_text}) or render_prompt("user/stage/intent_classify.j2", user_text=user_text)
        classification = self.classifier.classify_with_prompt(prompt, user_text_for_log=user_text)
        # 保存本轮分类结果，供“按五类意图选择 Prompt Profile”使用
        try:
            self._last_intent_category = str(classification.category.value)
            self._last_intent_confidence = float(classification.confidence)
        except Exception:
            self._last_intent_category = "UNCERTAIN"
            self._last_intent_confidence = 0.0
        self.logger.info(f"[bold cyan]意图识别结果: {classification.category.value}[/bold cyan] (置信度: {classification.confidence})")
        _ev("intent_classified", classification.model_dump())

        # Intent Registry 路由（规则优先）
        try:
            match = self.intent_router.route(user_text, project_id=self.project_id)
            self._current_intent_match = match
            # 新版 Phase1：只保存 intent 匹配结果，Planning Prompt 在 _build_planning_prompt 中直接三层渲染。
            _ev(
                "intent_routed",
                {
                    "name": match.name,
                    "source": match.source,
                    "confidence": match.confidence,
                    "matched_keywords": match.matched_keywords,
                    "tools": match.tools,
                    "risk_level": str(match.risk_level),
                    "mode": match.mode,
                    "reason": match.reason,
                    "prompt_ref": getattr(match, "prompt_ref", None),
                    "prompt_version": getattr(getattr(match, "intent", None), "prompt_version", None),
                },
            )
        except Exception as e:
            self.logger.warning(f"[IntentRouter] 路由失败，回退分类器: {e}")

        enable_planning = self.cfg.orchestrator.enable_planning
        if classification.category in (IntentCategory.CAPABILITY_QUERY, IntentCategory.GENERAL_CHAT, IntentCategory.CASUAL_CHAT):
            if enable_planning:
                self.logger.info("[dim]检测到能力询问或通用对话，跳过显式规划阶段。[/dim]")
                _ev(
                    "planning_skipped",
                    {
                        "reason": "capability_query_or_chat",
                        "category": classification.category.value,
                        "confidence": classification.confidence,
                    },
                )
                # 模式判定：聊天/规划
                enable_planning = False
        # 业界兜底：短文本 + UNCERTAIN 往往是问候/寒暄/无任务输入，不应进入规划
        # if classification.category == IntentCategory.UNCERTAIN:
        #     txt = (user_text or "").strip()
        #     if len(txt) <= 12 and any(k in txt for k in ("你好", "您好", "哈喽", "嗨", "hi", "hello", "在吗")):
        #         self.logger.info("[dim]短文本疑似问候（UNCERTAIN 兜底），跳过显式规划阶段。[/dim]")
        #         enable_planning = False
        return enable_planning

    def _execute_planning_phase(self, user_text: str, planning_prompt: str | None, trace_id: str, _ev: Callable[[str, dict[str, Any]], None], _llm_chat: Callable[[str, str | None], str]) -> Plan | None:
        return execute_planning_phase(self, user_text, planning_prompt, trace_id, _ev, _llm_chat)

    def _check_step_dependencies(self, step, plan: Plan, trace_id: str, _ev: Callable[[str, dict[str, Any]], None]) -> list[str]:
        return _exec_check_step_dependencies(self, step, plan, trace_id, _ev)

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
        return _exec_handle_tool_call_in_step(
            self, name, args, step, trace_id, keywords, confirm, _ev, _tool_result_to_message
        )

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
        return _exec_execute_single_step_iteration(
            self,
            step,
            step_cursor,
            plan,
            iteration,
            trace_id,
            keywords,
            confirm,
            _ev,
            _llm_chat,
            _try_parse_tool_call,
            _tool_result_to_message,
        )

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
        return _exec_handle_replanning(self, step, plan, replans_used, trace_id, tool_used, _ev, _llm_chat, _set_state)

    def _execute_final_verification(self, plan: Plan, did_modify_code: bool, trace_id: str, tool_used: bool, _ev: Callable[[str, dict[str, Any]], None], _set_state: Callable[[AgentState, dict[str, Any] | None], None]) -> AgentTurn | None:
        return _exec_execute_final_verification(self, plan, did_modify_code, trace_id, tool_used, _ev, _set_state)

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
        return _react_execute_react_fallback_loop(
            self,
            trace_id,
            keywords,
            confirm,
            events,
            _ev,
            _llm_chat,
            _try_parse_tool_call,
            _tool_result_to_message,
            _set_state,
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
        return _exec_execute_plan_steps(
            self,
            plan,
            trace_id,
            keywords,
            confirm,
            events,
            _ev,
            _llm_chat,
            _try_parse_tool_call,
            _tool_result_to_message,
            _set_state,
        )

    def _trim_history(self, *, max_messages: int) -> None:
        """
        高级对话历史裁剪，使用智能上下文管理和token预算。

        裁剪策略：
        1. 使用高级上下文管理器进行token-aware裁剪
        2. 优先保留高优先级内容（系统消息、当前任务相关）
        3. 智能压缩长内容以适应token预算
        4. 保持对话的连贯性和角色交替

        参数:
            max_messages: 最大保留消息数（兼容性参数，现主要使用token预算）

        流程图: 见 `agent_loop_trim_history_flow.svg`
        """
        from clude_code.orchestrator.advanced_context import get_advanced_context_manager, ContextPriority

        old_len = len(self.messages)
        if old_len <= 1:  # 至少保留system消息
            return

        # 初始化上下文管理器
        context_manager = get_advanced_context_manager(max_tokens=self.llm.max_tokens)

        # 清空旧上下文
        context_manager.clear_context(keep_system=True)

        # 添加system消息（最高优先级）
        if self.messages and self.messages[0].role == "system":
            system_content = self.messages[0].content or ""
            context_manager.add_system_context(system_content, ContextPriority.CRITICAL)

        # 添加对话历史（按优先级分类）
        for i, message in enumerate(self.messages[1:], 1):  # 跳过system消息
            # 根据位置和内容确定优先级
            if i >= len(self.messages) - 5:  # 最近5条消息
                priority = ContextPriority.HIGH
            elif i >= len(self.messages) - 15:  # 最近15条消息
                priority = ContextPriority.MEDIUM
            else:
                priority = ContextPriority.LOW

            context_manager.add_message(message, priority)

        # 获取优化后的上下文
        optimized_items = context_manager.optimize_context()

        # 重建消息列表
        new_messages = []

        # 添加system消息
        if self.messages and self.messages[0].role == "system":
            new_messages.append(self.messages[0])

        # 从优化后的上下文项重建消息
        for item in optimized_items:
            if item.category == "system":
                continue  # system消息已添加

            # 从metadata恢复原始消息
            original_role = item.metadata.get("original_role", item.category)
            message = ChatMessage(role=original_role, content=item.content)
            new_messages.append(message)

        # 如果优化后消息太少，至少保留最近的几条
        if len(new_messages) < 3 and len(self.messages) > 3:
            # 保留system + 最后两条对话
            new_messages = [self.messages[0]] + self.messages[-4:] if len(self.messages) > 4 else self.messages

        self.messages = new_messages

        # 记录裁剪统计
        stats = context_manager.get_context_stats()
        self.logger.debug(
            f"[dim]智能上下文裁剪: {old_len} → {len(self.messages)} 条消息, "
            f"{stats.get('total_tokens', 0)} tokens ({stats.get('utilization_rate', 0):.1%})[/dim]"
        )

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
            #keys = list(payload.keys())[:3]
            #return f"成功: {', '.join(keys)}{'...' if len(payload) > 3 else ''}"
            keys = list(payload.keys()) if isinstance(payload, dict) else []
            keys_preview = keys[:8]
            more = "…" if len(keys) > len(keys_preview) else ""
            return f"成功: payload_keys={keys_preview}{more}"

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
        return _dispatch_tool_fn(self, name, args)

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
        return _semantic_search_fn(self, query)

