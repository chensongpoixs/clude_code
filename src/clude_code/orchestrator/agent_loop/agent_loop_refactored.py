"""
重构后的 AgentLoop 核心模块
只保留主要的 AgentLoop 类和基础导入，其他功能模块化到独立文件
"""
import re
import uuid
from pathlib import Path
from typing import Any, Callable, List, Dict, Optional

# ============================================================================
# 核心导入
# ============================================================================

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
from clude_code.orchestrator.state_m import AgentState
from clude_code.orchestrator.models import AgentTurn

# 导入新的模块化组件
from .control_protocol import (
    MasterController, 
    get_execution_controller, 
    get_state_manager, 
    get_error_handler, 
    reset_global_state
)

from .models import get_model_manager as get_model_manager_fn

# ============================================================================
# 核心导入 (保持向后兼容)
# ============================================================================

# 导入规划相关 (临时，后续会重构)
from .planning import execute_planning_phase

# 导入执行相关 (临时，后续会重构)  
from .execution import (
    execute_plan_steps,
    execute_single_step_iteration,
    handle_replanning as _exec_handle_replanning,
    execute_final_verification as _exec_execute_final_verification
)

# 导入 LLM 相关
from .llm_io import (
    build_user_content,
    build_system_prompt,
    _ev,
    llm_chat,
    log_llm_response_data_to_file,
    log_llm_request_data_to_file,
    _llm_chat,
    get_llm_response,
)

# 导入提示词相关
from .prompts import SYSTEM_PROMPT, load_project_memory

# ============================================================================
# 主要的 AgentLoop 类 (精简版)
# ============================================================================

class AgentLoop:
    """重构后的 AgentLoop 核心类
    
    专注于主要功能和协调，具体实现委托给模块化组件
    """
    
    def __init__(self, cfg: CludeConfig, session_id: str | None = None):
        """初始化 AgentLoop"""
        self.cfg = cfg
        self.session_id = session_id or f"sess_{id(self)}"
        
        # 日志记录
        self.logger = get_logger(
            __name__,
            workspace_root=cfg.workspace_root,
            log_to_console=cfg.logging.log_to_console,
            level=cfg.logging.level,
            log_format=cfg.logging.log_format,
            date_format=cfg.logging.date_format,
        )
        
        # 专用日志记录 (只写入文件)
        self.file_only_logger = get_logger(
            f"{__name__}.llm_detail",
            workspace_root=cfg.workspace_root,
            log_to_console=False,
            level=cfg.logging.level,
            log_file=cfg.logging.file_path,
            max_bytes=cfg.logging.max_bytes,
            backup_count=cfg.logging.backup_count,
            log_format=cfg.logging.log_format,
            date_format=cfg.logging.date_format,
        )
        
        # 初始化工具配置
        try:
            from clude_code.config import set_tool_configs
            from clude_code.tooling.weather import set_weather_config
            set_tool_configs(cfg)
        except ImportError:
            pass
        
        # 创建核心组件
        self.tools = LocalTools(
            cfg.workspace_root,
            max_file_read_bytes=cfg.limits.max_file_read_bytes,
            max_output_bytes=cfg.limits.max_output_bytes,
        )
        
        # 绑定模型管理器
        self._model_manager = get_model_manager_fn()
        self._model_manager.bind(self.llm)
        
        # 认证、会话、使用、知识系统
        self.audit = AuditLogger(cfg.workspace_root, self.session_id)
        self.trace = TraceLogger(cfg.workspace_root, self.session_id)
        self.usage = SessionUsage()
        
        # 创建新的控制器
        self._controller = MasterController()
        
        # 初始化上下文相关
        self._turn_modified_paths: set[Path] = set()
        self._current_ev: Optional[Callable[[str, dict[str, Any]], None]] = None
        self._current_trace_id: Optional[str] = None
        
        # 初始化状态
        self._current_profile: Optional['PromptProfile'] = None
        self._current_risk_level: Optional[str] = None
        
        # 初始化 Repo Map 和项目记忆
        raw_repo_map = self.tools.generate_repo_map()
        
        # Repo Map 大小保护：最多占用 20% 的 token 预算
        max_repo_map_chars = int(self.llm.max_tokens * 0.2 * 3.5)
        if len(raw_repo_map) > max_repo_map_chars:
            self._repo_map = raw_repo_map[:max_repo_map_chars] + f"\\n... [repo_map 已截断，原长度: {len(raw_repo_map)} chars]"
        
        # 初始化系统提示词
        combined_system_prompt = self._build_system_prompt_from_profile(None)
        
        self.logger.info(f"[dim]初始化 AgentLoop，session_id={self.session_id}[/dim]")
    
    # ============================================================================
    # 公共接口 (保持向后兼容)
    # ============================================================================
    
    @property
    def messages(self) -> List[ChatMessage]:
        """获取消息历史"""
        # 这里应该从上下文管理器获取，暂时返回空列表
        return []
    
    @property
    def llm(self) -> LlamaCppHttpClient:
        """获取 LLM 客户端"""
        return self.llm
    
    @property
    def workspace_root(self) -> str:
        """获取工作区根目录"""
        return self.cfg.workspace_root
    
    @property
    def cfg(self) -> CludeConfig:
        """获取配置对象"""
        return self.cfg
    
    # ============================================================================
    # 核心执行方法 (简化版，委托给控制器)
    # ============================================================================
    
    def run_turn(self, prompt: str, confirm: Optional[Callable[[str], bool]] = None, debug: bool = False, output_format: str = "text") -> 'AgentTurn':
        """执行一轮对话 (简化版，委托给控制器)"""
        self.logger.info(f"[bold cyan]开始新的一轮对话[/bold cyan] trace_id=trace_{uuid.uuid().hex[:12]}")
        
        # 初始化执行上下文
        context = self._controller.execution_controller.initialize(
            session_id=self.session_id,
            trace_id=f"trace_{uuid.uuid().hex[:12]}",
            max_steps=self.cfg.orchestrator.max_plan_steps
        )
        
        try:
            # 记录开始
            self._controller.state_manager.save_state(context, {
                "action": "turn_start",
                "prompt": prompt,
                "debug": debug,
                "output_format": output_format
            })
            
            # 执行主逻辑 (委托给控制器)
            final_signal = self._controller.execute_turn(context, prompt)
            
            # 处理最终信号
            if final_signal.action in ["complete", "step_done"]:
                self._controller.state_manager.save_state(context, {
                    "action": "turn_end",
                    "final_action": final_signal.action,
                    "reason": final_signal.reason
                })
                return AgentTurn(
                    llm_response=get_llm_response(),
                    llm_request_data=get_llm_request_data(),
                    llm_chat_history=[],
                    tool_calls=[],
                    tool_results=[],
                    did_modify_code=False,
                    trace_id=context.trace_id
                )
            else:
                # 处理其他信号 (replan, retry, abort)
                return AgentTurn(
                    llm_response=get_llm_response(),
                    llm_request_data=get_llm_request_data(),
                    llm_chat_history=[],
                    tool_calls=[],
                    tool_results=[],
                    did_modify_code=False,
                    trace_id=context.trace_id
                )
        
        except Exception as e:
            self.logger.error(f"执行对话失败: {e}")
            return AgentTurn(
                llm_response=get_llm_response(),
                llm_request_data=get_llm_request_data(),
                llm_chat_history=[],
                tool_calls=[],
                tool_results=[],
                did_modify_code=False,
                trace_id=context.trace_id
            )
    
    # ============================================================================
    # 系统提示词构建 (保持向后兼容)
    # ============================================================================
    
    def _build_system_prompt_from_profile(self, profile: Optional['PromptProfile']) -> str:
        """构建系统提示词"""
        if profile is not None:
            try:
                combined_system_prompt = profile.get_system_prompt(
                    tools_section=self._tools_section,
                    project_memory=self._project_memory_text.strip() if self._project_memory_text else "",
                    env_info=f"{self._env_info}\\n\\n=== 代码仓库符号概览 ===\\n{self._repo_map}",
                )
                self.logger.debug(f"[dim]使用 Profile '{profile.name}' 构建 System Prompt[/dim]")
                return combined_system_prompt
            except Exception as e:
                self.logger.warning(f"[yellow]Profile System Prompt 构建失败: {e}，降级使用默认[/yellow]")
        
        # 降级：使用默认 SYSTEM_PROMPT
        combined = (
            f"{SYSTEM_PROMPT}"
            f"{self._project_memory_text}"
            f"\\n\\n=== 环境信息 ===\\n{self._env_info}\\n\\n=== 代码仓库符号概览 ===\\n{self._repo_map}"
        )
        
        # 系统提示词大小保护：最多占用 50% 的 token 预算
        max_system_chars = int(self.llm.max_tokens * 0.5 * 3.5)
        if len(combined) > max_system_chars:
            self.logger.warning(
                f"[yellow]⚠ 系统提示词过大: {len(combined)} chars > {max_system_chars} chars (50% token budget)[/yellow]"
            combined = combined[:max_system_chars] + "\\n... [系统提示词已截断]"
        
        return combined
    
    # ============================================================================
    # 属性和方法 (简化版)
    # ============================================================================
    
    @property
    def _tools_section(self) -> str:
        """获取工具清单字符串"""
        # 这里应该从工具管理器获取，暂时返回空字符串
        return ""
    
    @property
    def _project_memory_text(self) -> str:
        """获取项目记忆文本"""
        # 这里应该从记忆系统获取，暂时返回空字符串
        return ""
    
    @property
    def _env_info(self) -> str:
        """获取环境信息"""
        # 这里应该从环境探测器获取，暂时返回基本环境信息
        return f"操作系统: {os.name} (10)\\n当前绝对路径: {os.getcwd()}"
    
    @property
    def _repo_map(self) -> str:
        """获取仓库图谱"""
        return self._repo_map

# ============================================================================
# 导出 (保持向后兼容)
# ============================================================================

# 向后兼容的导出
__all__ = ["AgentLoop"]