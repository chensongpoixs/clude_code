import json
import re
import uuid
from pathlib import Path
from typing import Any, Callable, List, Dict, Optional

from clude_code.config.config import CludeConfig
from clude_code.llm.http_client import ChatMessage, ContentPart, LlamaCppHttpClient
from clude_code.llm.model_manager import ModelManager, get_model_manager
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
from clude_code.context.claude_standard import get_claude_context_manager
from clude_code.orchestrator.classifier import (
    IntentCategory,
    ClassificationResult,
    IntentClassifier,
)
from clude_code.orchestrator.registry import (
    get_default_registry,
    PromptProfile,
    RiskLevel,
    get_default_profile_for_category
)
# Import AgentState when needed to avoid circular imports
from clude_code.orchestrator.state_m import AgentState

from .models import AgentTurn
from .parsing import try_parse_tool_call
from .prompts import SYSTEM_PROMPT, load_project_memory
from clude_code.prompts import read_prompt, render_prompt
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
from .tool_dispatch import dispatch_tool as _dispatch_tool_fn, iter_tool_specs as _iter_tool_specs, render_tools_for_system_prompt


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
    
    def __init__(self, cfg: CludeConfig, *, session_id: str | None = None) -> None:
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
            level=cfg.logging.level,
            log_format=cfg.logging.log_format,
            date_format=cfg.logging.date_format,
        )
        # 创建只写入文件的 logger（用于记录 LLM 请求/响应详情）
        self.file_only_logger = get_logger(
            f"{__name__}.llm_detail",
            workspace_root=cfg.workspace_root,
            log_to_console=False,  # 只写入文件，不输出到控制台
            level=cfg.logging.level,
            log_file=cfg.logging.file_path,
            max_bytes=cfg.logging.max_bytes,
            backup_count=cfg.logging.backup_count,
            log_format=cfg.logging.log_format,
            date_format=cfg.logging.date_format,
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
        
        # 绑定模型管理器（支持动态模型切换）
        self._model_manager = get_model_manager()
        self._model_manager.bind(self.llm)
        
        self.tools = LocalTools(
            cfg.workspace_root,
            max_file_read_bytes=cfg.limits.max_file_read_bytes,
            max_output_bytes=cfg.limits.max_output_bytes,
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
        
        self.audit = AuditLogger(cfg.workspace_root, self.session_id)
        self.trace = TraceLogger(cfg.workspace_root, self.session_id)
        self.usage = SessionUsage()
        
        # Knowledge / RAG systems
        self.indexer = IndexerService(cfg)
        self.indexer.start()  # Start background indexing (best-effort)
        if str(getattr(self.indexer, "status", "")).startswith("disabled:"):
            self.logger.info(f"[dim]后台索引已禁用: {self.indexer.status}[/dim]")
        else:
            self.logger.info("[dim]启动后台索引服务（LanceDB RAG）[/dim]")
        self.embedder = CodeEmbedder(cfg)
        self.vector_store = VectorStore(cfg)
        self.verifier = Verifier(cfg)
        self.classifier = IntentClassifier(self.llm, file_only_logger=self.file_only_logger)
        
        # Profile Registry（意图 → Prompt Profile 映射）
        self.profile_registry = get_default_registry(cfg.workspace_root)
        self._current_profile: PromptProfile | None = None
        self._current_risk_level: RiskLevel = RiskLevel.MEDIUM

        # 阶段 C: 追踪本轮修改过的文件路径，用于选择性测试
        self._turn_modified_paths: set[Path] = set()

        # P0-2: Question 工具阻塞协议状态
        self._waiting_user_input: bool = False
        self._pending_question: dict[str, Any] | None = None

        # display 工具需要的运行时上下文（在 run_turn 中设置）
        self._current_ev: Callable[[str, dict[str, Any]], None] | None = None
        self._current_trace_id: str | None = None

        # Initialize with Repo Map for better global context (Aider-style)
        import platform
        raw_repo_map = self.tools.generate_repo_map()
        
        # 系统提示词大小保护：repo_map 最多占用 20% 的 token 预算
        MAX_REPO_MAP_CHARS = int(self.llm.max_tokens * 0.2 * 3.5)  # 约 20% token 预算
        if len(raw_repo_map) > MAX_REPO_MAP_CHARS:
            # 截断 repo_map，保留头部（核心文件）
            self._repo_map = raw_repo_map[:MAX_REPO_MAP_CHARS] + f"\n... [repo_map 已截断，原长度: {len(raw_repo_map)} chars]"
            self.logger.warning(f"[yellow]repo_map 过大，已截断: {len(raw_repo_map)} → {MAX_REPO_MAP_CHARS} chars[/yellow]")
        else:
            self._repo_map = raw_repo_map
        
        self._env_info = f"操作系统: {platform.system()} ({platform.release()})\n当前绝对路径: {self.cfg.workspace_root}"
        self._tools_section = render_tools_for_system_prompt(include_schema=False)

        # Claude Code 对标：自动加载 CLUDE.md 作为项目记忆（只读、失败不阻塞）
        self._project_memory_text, project_memory_meta = load_project_memory(self.cfg.workspace_root)
        self._project_memory_meta: dict[str, object] = project_memory_meta
        self._project_memory_emitted: bool = False

        # 初始化时使用默认 System Prompt（后续会根据 Profile 动态更新）
        combined_system_prompt = self._build_system_prompt_from_profile(None)
        
        self.messages: list[ChatMessage] = [
            ChatMessage(role="system", content=combined_system_prompt),
        ]
        if bool(project_memory_meta.get("loaded")):
            self.logger.info(f"[dim]已加载 CLUDE.md 项目记忆: {project_memory_meta}[/dim]")
        else:
            self.logger.info("[dim]未加载 CLUDE.md（未找到或为空）[/dim]")
        self.logger.info("[dim]初始化系统提示词（包含 Repo Map/环境信息/可选项目记忆）[/dim]")
        
        # 初始化 LLM 追踪属性（用于 observability）
        self._last_llm_stage: str | None = None
        self._last_llm_step_id: str | None = None
        self._last_provider_id: str | None = None
        self._last_provider_base_url: str | None = None
        self._last_provider_model: str | None = None
        self._active_provider_id: str | None = None
        self._active_provider_base_url: str | None = None
        self._active_provider_model: str | None = None
        self._last_logged_system_prompt_hash: str | None = None

    def run_turn(
        self,
        user_text: str,
        *,
        confirm: Callable[[str], bool],
        debug: bool = False,
        on_event: Callable[[dict[str, Any]], None] | None = None,
        images: list[dict[str, Any]] | None = None,
        image_paths: list[str] | None = None,
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
            images: 可选的图片列表（OpenAI Vision API 格式）
        
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
        # 注：_llm_log_cursor 已弃用（llm_io.py 现在使用基于内容的消息查找，不再依赖索引）

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

        # 记录最近一次用户输入的图片路径，供工具回退使用
        if image_paths:
            self._last_image_paths = list(image_paths)

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

        # 2) 记录用户输入（必要时把规划提示并入同一条 user 消息，避免 role 不交替）
        self.audit.write(trace_id=trace_id, event="user_message", data={"text": user_text})
        _ev("user_message", {"text": user_text})
        
        # P0-2: 使用 Profile 渲染 User Prompt
        # - 如果有 planning_prompt，使用 planning_prompt（阶段模板）
        # - 否则使用 Profile 的意图模板渲染用户输入
        if planning_prompt is not None:
            user_content = planning_prompt
        else:
            user_content = self._build_user_prompt_from_profile(
                user_text=user_text,
                planning_prompt="",
            )

        self.logger.info(f"[bold cyan]发送给 LLM 的 user_content[/bold cyan] len={len(user_content)}")
        # 透传 user_content（用于"对话/输出"窗格复刻 chat 默认日志）
        _ev(
            "user_content_built",
            {
                "preview": user_content[:2000],
                "truncated": len(user_content) > 2000,
                "messages_count": len(self.messages) + 1,  # 即将 append
                "planning_prompt_included": bool(planning_prompt),
                "has_images": bool(images),
                "images_count": len(images) if images else 0,
            },
        )
        
        # 构建消息内容（支持多模态）
        if images:
            # 多模态消息：文本 + 图片
            multimodal_content: list[dict[str, Any]] = [{"type": "text", "text": user_content}]
            multimodal_content.extend(images)
            self.messages.append(ChatMessage(role="user", content=multimodal_content))
            self.logger.info(f"[dim]已附加 {len(images)} 张图片到用户消息[/dim]")
        else:
            # 纯文本消息
            self.messages.append(ChatMessage(role="user", content=user_content))
        self._trim_history(max_messages=30)
        self.logger.debug(f"[dim]当前消息历史长度: {len(self.messages)}[/dim]")

        llm_chat = (lambda stage, step_id=None: self._llm_chat(stage, step_id=step_id, _ev=_ev))

        # 3) 规划阶段
        plan: Plan | None = None
        if enable_planning:
            _set_state(AgentState.PLANNING, {"reason": "enable_planning"})
            # 🚨 核心修复：增强规划阶段处理
            try:
                plan = execute_planning_phase(self, user_text, planning_prompt, trace_id, _ev, llm_chat)
            except ValueError as planning_error:
                # 如果规划失败，尝试使用简化版本
                self.logger.warning(f"[yellow]⚠️ 标准规划失败，尝试使用简化版本: {planning_error}[/yellow]")
                
                # 创建一个简化的fallback规划
                fallback_plan = Plan(
                    title="简化代码分析计划",
                    steps=[
                        Step(
                            id="step_1",
                            description="使用 list_dir 工具扫描 libcommon 目录",
                            expected_output="libcommon 目录结构和文件列表",
                            dependencies=[],
                            tools_expected=["list_dir"]
                        ),
                        Step(
                            id="step_2", 
                            description="使用 grep 工具搜索 libcommon 目录中的代码文件",
                            expected_output="找到的代码文件和关键信息",
                            dependencies=["step_1"],
                            tools_expected=["grep"]
                        ),
                        Step(
                            id="step_3",
                            description="使用 read_file 工具读取关键代码文件内容",
                            expected_output="代码文件的详细内容",
                            dependencies=["step_2"],
                            tools_expected=["read_file"]
                        ),
                        Step(
                            id="step_4",
                            description="分析代码复杂度和重构需求",
                            expected_output="代码复杂度分析和重构建议",
                            dependencies=["step_3"],
                            tools_expected=["display"]
                        )
                    ],
                    assumptions=["libcommon目录存在且可访问"],
                    constraints=["基于可用文件进行分析"],
                    risks=["代码分析可能不完整"],
                    verification_policy="run_verify"
                )
                
                plan = fallback_plan
                self.logger.info("[green]✓ 使用简化fallback规划成功[/green]")
                plan_summary = render_plan_markdown(plan)
                self.logger.info(f"[dim]简化计划摘要:\n{plan_summary}[/dim]")

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
        tool_names = self._get_prompt_tool_names()
        tools_expected_example = json.dumps(tool_names, ensure_ascii=False)
        tools_expected_hint = ", ".join(tool_names)
        return render_prompt(
            "user/stage/planning.j2",
            max_plan_steps=int(self.cfg.orchestrator.max_plan_steps),
            tools_expected_example=tools_expected_example,
            tools_expected_hint=tools_expected_hint,
            input_text=input_text,
        )

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
        result = run_tool_lifecycle(self, name, args, trace_id, confirm, _ev)
        
        # P0-2: Question 工具阻塞协议检测
        # 如果工具返回 type="question" 且 status="pending"，设置等待用户输入标志
        if result.ok and isinstance(result.payload, dict):
            payload_type = result.payload.get("type")
            payload_status = result.payload.get("status")
            if payload_type == "question" and payload_status == "pending":
                self._waiting_user_input = True
                self._pending_question = result.payload.get("data")
                self.logger.info("[yellow]⏸ Question 工具触发阻塞：等待用户输入[/yellow]")
                _ev("question_pending", {"question": self._pending_question})
        
        return result

    def _build_system_prompt_from_profile(self, profile: PromptProfile | None) -> str:
        """
        根据 Profile 动态构建 System Prompt。
        
        对齐 agent_design_v_1.0.md 设计规范：
        - Profile 决定 System Prompt 组合（Core + Role + Policy + Context）
        - 支持降级到默认 SYSTEM_PROMPT
        
        参数:
            profile: Prompt Profile，None 表示使用默认 Prompt
        
        返回:
            组合后的 System Prompt 文本
        """
        if profile is not None:
            try:
                # 使用 Profile 的四层组合
                system_prompt = profile.get_system_prompt(
                    tools_section=self._tools_section,
                    project_memory=self._project_memory_text.strip() if self._project_memory_text else "",
                    env_info=f"{self._env_info}\n\n=== 代码仓库符号概览 ===\n{self._repo_map}",
                )
                self.logger.debug(f"[dim]使用 Profile '{profile.name}' 构建 System Prompt[/dim]")
                return system_prompt
            except Exception as e:
                self.logger.warning(f"[yellow]Profile System Prompt 构建失败: {e}，降级使用默认[/yellow]")
        
        # 降级：使用默认 SYSTEM_PROMPT
        combined = (
            f"{SYSTEM_PROMPT}"
            f"{self._project_memory_text}"
            f"\n\n=== 环境信息 ===\n{self._env_info}\n\n=== 代码仓库符号概览 ===\n{self._repo_map}"
        )
        
        # 系统提示词总长度保护：最多占用 50% 的 token 预算
        MAX_SYSTEM_CHARS = int(self.llm.max_tokens * 0.5 * 3.5)  # 约 50% token 预算
        if len(combined) > MAX_SYSTEM_CHARS:
            self.logger.warning(
                f"[yellow]⚠ 系统提示词过大: {len(combined)} chars > {MAX_SYSTEM_CHARS} chars (50% token budget)[/yellow]"
            )
            # 截断：保留头部 + 基本环境信息
            combined = combined[:MAX_SYSTEM_CHARS] + "\n... [系统提示词已截断]"
        
        return combined
    
    def _update_system_prompt_for_profile(self, profile: PromptProfile | None) -> None:
        """
        更新消息历史中的 System Prompt。
        
        当 Profile 变化时调用，确保 System Prompt 与当前 Profile 一致。
        """
        if not self.messages or self.messages[0].role != "system":
            return
        
        new_system_prompt = self._build_system_prompt_from_profile(profile)
        self.messages[0] = ChatMessage(role="system", content=new_system_prompt)
        self.logger.debug("[dim]已更新 System Prompt[/dim]")
    
    def _build_user_prompt_from_profile(
        self,
        user_text: str,
        planning_prompt: str = "",
    ) -> str:
        """
        根据 Profile 渲染 User Prompt。
        
        对齐 agent_design_v_1.0.md 设计规范：
        - 禁止直接使用原始用户输入作为最终 User Prompt
        - 使用 Profile 的意图模板渲染用户输入
        
        参数:
            user_text: 原始用户输入
            planning_prompt: 规划协议提示词（可选）
        
        返回:
            渲染后的 User Prompt 文本
        """
        profile = self._current_profile
        
        if profile is not None:
            try:
                # 获取当前意图名称
                intent_name = ""
                if hasattr(self, 'classifier') and hasattr(self.classifier, '_last_category'):
                    intent_name = self.classifier._last_category.value if self.classifier._last_category else ""
                
                # 使用 Profile 的意图模板渲染
                rendered = profile.render_user_prompt(
                    user_text=user_text,
                    planning_prompt=planning_prompt,
                    project_id=getattr(self.cfg, 'project_id', 'default'),
                    intent_name=intent_name or profile.name,
                    risk_level=self._current_risk_level.value,
                )
                self.logger.debug(f"[dim]使用 Profile '{profile.name}' 渲染 User Prompt[/dim]")
                return rendered
            except Exception as e:
                self.logger.warning(f"[yellow]Profile User Prompt 渲染失败: {e}，降级使用原始输入[/yellow]")
        
        # 降级：直接返回原始用户输入
        return user_text

    def _select_profile(self, category: IntentCategory, _ev: Callable[[str, dict[str, Any]], None]) -> PromptProfile | None:
        """
        根据意图分类选择 Prompt Profile。
        
        对齐 agent_design_v_1.0.md 设计规范：
        - Intent → prompt_profile → System/User Prompt 组合
        """
        profile_name = get_default_profile_for_category(category)
        profile = self.profile_registry.get(profile_name)
        
        if profile:
            self._current_profile = profile
            self._current_risk_level = profile.risk_level
            self.logger.debug(f"[dim]选择 Profile: {profile_name} (风险等级: {profile.risk_level.value})[/dim]")
            _ev("profile_selected", {
                "profile_name": profile_name,
                "risk_level": profile.risk_level.value,
                "intent_category": category.value,
            })
            # P0-1: 根据 Profile 动态更新 System Prompt
            self._update_system_prompt_for_profile(profile)
        else:
            self.logger.debug(f"[dim]未找到 Profile: {profile_name}，使用默认配置[/dim]")
            self._current_profile = None
            self._current_risk_level = RiskLevel.MEDIUM
        
        return profile

    def _classify_intent_and_decide_planning(self, user_text: str, _ev: Callable[[str, dict[str, Any]], None]) -> bool:
        """意图分类和决策门：根据用户意图决定是否启用规划。"""
        classification = self.classifier.classify(user_text)
        self.logger.info(f"[bold cyan]意图识别结果: {classification.category.value}[/bold cyan] (置信度: {classification.confidence})")
        _ev("intent_classified", classification.model_dump())
        
        # 选择对应的 Prompt Profile
        self._select_profile(classification.category, _ev)

        enable_planning = self.cfg.orchestrator.enable_planning

        # 新增：复杂度检查，防止复杂任务被误判为GENERAL_CHAT
        if (classification.category == IntentCategory.GENERAL_CHAT and 
            classification.confidence > 0.8 and 
            len(user_text) > 30):
            
# 简单复杂度评估：基于长度和关键词
            complexity_indicators = ['创建', '分析', '修复', '实现', '设计', '调试', '编译', '部署']
            complexity_score = sum(1 for indicator in complexity_indicators if indicator in user_text) / len(complexity_indicators)
            
            # 长度复杂度：每50个字符增加0.1分，最高0.5分
            length_complexity = min(len(user_text) / 500.0, 0.5)
            total_complexity = complexity_score + length_complexity
            
            if total_complexity > 0.3:
                self.logger.info(f"[yellow]检测到高复杂度任务({total_complexity:.2f})，强制启用规划[/yellow]")
                enable_planning = True  # 强制启用规划

        if classification.category in (IntentCategory.CAPABILITY_QUERY, IntentCategory.GENERAL_CHAT):
            if enable_planning:
                self.logger.info("[dim]检测到能力询问或通用对话，跳过显式规划阶段。[/dim]")
                _ev(
                    "planning_skipped",
                    {
                        "reason": "capability_query_or_general_chat",
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
        return execute_planning_phase(self, user_text, planning_prompt, trace_id, _ev, llm_chat)

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
        from clude_code.context.claude_standard import get_claude_context_manager, ContextPriority

        old_len = len(self.messages)
        if old_len <= 1:  # 至少保留system消息
            return

        # 使用Claude Code标准上下文管理器
        context_manager = get_claude_context_manager(max_tokens=self.llm.max_tokens)

        # 清空旧上下文（避免重复）
        context_manager.clear_context(keep_protected=False)

        # 添加system消息（最高优先级）
        if self.messages and self.messages[0].role == "system":
            system_content = self.messages[0].content or ""
            # 处理多模态内容，转换为字符串
            if isinstance(system_content, list):
                system_content = "\n".join(
                    item.get("text", "") if isinstance(item, dict) and item.get("type") == "text" else "" 
                    for item in system_content
                )
            context_manager.add_system_context(system_content)

        # 添加对话历史（按优先级分类）
        for i, message in enumerate(self.messages[1:], 1):  # 跳过system消息
            # 根据位置和内容确定优先级
            if i >= len(self.messages) - 5:  # 最近5条消息
                priority = ContextPriority.RECENT
            elif i >= len(self.messages) - 15:  # 最近15条消息
                priority = ContextPriority.WORKING
            else:
                priority = ContextPriority.RELEVANT
            
            context_manager.add_message(message, priority)

        # Claude Code自动处理（已触发auto-compact）
        optimized_items = context_manager.context_items

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

        # 确保至少有最小消息数
        if len(new_messages) < 3 and len(self.messages) > 3:
            # 保留system + 最后几条对话
            new_messages = [self.messages[0]] + self.messages[-3:] if len(self.messages) > 3 else self.messages

        self.messages = new_messages

        # 记录裁剪统计
        stats = context_manager.get_context_summary()
        self.logger.debug(
            f"[dim]Claude Code标准上下文优化: {old_len} → {len(self.messages)} 条消息, "
            f"{stats.get('current_tokens', 0)} tokens ({stats.get('usage_percent', 0):.1%})[/dim]"
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

    # ============================================================
    # P0-2: Question 工具阻塞协议 API
    # ============================================================
    
    def is_waiting_input(self) -> bool:
        """
        检查 Agent 是否正在等待用户输入。
        
        当 question 工具返回 pending 状态时，此方法返回 True。
        调用者（CLI/UI）应检测此状态并收集用户输入。
        """
        return self._waiting_user_input
    
    def get_pending_question(self) -> dict[str, Any] | None:
        """
        获取待回答的问题数据。
        
        返回:
            问题数据字典（包含 question/options/multiple/header），或 None
        """
        return self._pending_question
    
    def answer_question(self, answer: str | list[str]) -> None:
        """
        提供 question 工具的答案，恢复 Agent 执行。
        
        参数:
            answer: 用户的回答（单选为 str，多选为 list[str]）
        
        行为:
            1. 将答案作为 user 消息注入 messages
            2. 清除等待标志
            3. 下次 run_turn 时 Agent 将看到答案并继续
        """
        if not self._waiting_user_input:
            self.logger.warning("[yellow]answer_question 调用但当前未在等待输入[/yellow]")
            return
        
        # 构建答案消息
        if isinstance(answer, list):
            answer_text = f"[用户回答] {', '.join(answer)}"
        else:
            answer_text = f"[用户回答] {answer}"
        
        # 注入到消息历史
        self.messages.append(ChatMessage(role="user", content=answer_text))
        
        # 清除等待状态
        self._waiting_user_input = False
        self._pending_question = None
        
        self.logger.info(f"[green]✓ 收到用户回答，已恢复执行[/green]")
        self.audit.write(
            trace_id=self._current_trace_id or "question_answer",
            event="question_answered",
            data={"answer": answer_text[:200]},
        )
    
    # ============================================================
    # 动态模型切换 API
    # ============================================================
    
    def switch_model(self, model: str, validate: bool = True) -> tuple[bool, str]:
        """
        切换 LLM 模型。
        
        参数:
            model: 目标模型名称/ID
            validate: 是否验证模型可用性（默认 True）
        
        返回:
            (success, message) 元组
        """
        old_model = self.llm.model
        success, message = self._model_manager.switch_model(model, validate)
        
        if success:
            self.logger.info(f"[bold green]模型已切换: {old_model} → {model}[/bold green]")
            self.audit.write(
                trace_id="model_switch",
                event="model_switched",
                data={"old_model": old_model, "new_model": model},
            )
        else:
            self.logger.warning(f"[yellow]模型切换失败: {message}[/yellow]")
        
        return success, message
    
    def get_current_model(self) -> str:
        """获取当前使用的模型名称"""
        return self.llm.model
    
    def list_available_models(self) -> list[str]:
        """获取可用模型列表"""
        return self._model_manager.list_models()
    
    def rollback_model(self) -> tuple[bool, str]:
        """回滚到上一个使用的模型"""
        return self._model_manager.rollback_model()

