"""
display 工具实现：让 Agent 能够在执行过程中主动向用户输出信息。

业界对标：
- Claude Code: message_user
- Cursor: thinking + message
- OpenAI Assistants: code_interpreter 输出

使用场景：
- 长任务中途汇报进度
- 多步骤任务的分段说明
- 分析结论的中间输出
- 需要用户确认前的说明
"""
from typing import TYPE_CHECKING, Any, Callable

from clude_code.tooling.types import ToolResult
from ..logger_helper import get_tool_logger
from ...config.tools_config import get_display_config

# 工具模块 logger（延迟初始化）
_logger = get_tool_logger(__name__)

if TYPE_CHECKING:
    from clude_code.orchestrator.agent_loop import AgentLoop


# 消息级别对应的 Rich 颜色
LEVEL_COLORS = {
    "info": "cyan",
    "success": "green",
    "warning": "yellow",
    "error": "red",
    "progress": "blue",
}

# 消息级别对应的 emoji
LEVEL_EMOJI = {
    "info": "ℹ️",
    "success": "✅",
    "warning": "⚠️",
    "error": "❌",
    "progress": "🔄",
}

MAX_CONTENT_LENGTH = 10000  # 最大内容长度


def display(
    loop: "AgentLoop",
    content: str,
    level: str = "info",
    title: str | None = None,
    thought: str | None = None,
    explanation: str | None = None,
    evidence: list[str] | None = None,
    *,
    _ev: Callable[[str, dict[str, Any]], None] | None = None,
    trace_id: str | None = None,
) -> ToolResult:
    """
    向用户输出信息（进度、分析结果、说明等）。
    
    参数:
        loop: AgentLoop 实例（用于访问 logger、audit 等）
        content: 要显示的内容（支持 Markdown）
        level: 消息级别（info/success/warning/error/progress）
        title: 可选标题
        _ev: 事件回调（用于 --live 模式的实时 UI 更新）
        trace_id: 追踪 ID（用于审计日志）
    
    返回:
        ToolResult 对象
    
    实现原理:
        1. 验证参数（content 非空、level 有效）
        2. 截断超长内容
        3. 通过事件机制广播到 UI（--live 模式）
        4. 降级方案：通过 logger 输出到控制台
        5. 记录到审计日志
        6. 返回成功结果
    """
    # 1. 参数验证
    # 检查工具是否启用
    config = get_display_config()
    if not config.enabled:
        _logger.warning("[Display] 显示工具已被禁用")
        return ToolResult(False, error={"code": "E_TOOL_DISABLED", "message": "display tool is disabled"})

    _logger.debug(f"[Display] 开始显示消息: level={level}, title={title}, content_length={len(content)}")
    if not content or not content.strip():
        _logger.warning("[Display] 内容为空，拒绝显示")
        return ToolResult(
            ok=False,
            error={"code": "E_INVALID_ARGS", "message": "content 不能为空"},
        )
    
    # 2. 规范化 level
    if level not in LEVEL_COLORS:
        _logger.warning(f"[Display] 无效的消息级别: {level}，使用默认值 info")
        level = "info"
    
    # 3. 截断超长内容
    truncated = False
    if len(content) > MAX_CONTENT_LENGTH:
        content = content[:MAX_CONTENT_LENGTH] + "\n... (内容已截断)"
        truncated = True
        _logger.warning(f"[Display] 内容过长，已截断: {len(content)} -> {MAX_CONTENT_LENGTH}")
    
    # 4. 构造显示数据
    # 说明：
    # - thought/explanation 用于把“为什么/怎么想的”展示到 live UI 的 Why 区域（可选）
    # - evidence 用于展示要点列表（可选）
    display_data = {
        "content": content,
        "level": level,
        "title": title,
        "thought": thought,
        "explanation": explanation,
        "evidence": evidence,
        "truncated": truncated,
    }
    
    # 5. 通过事件机制广播到 UI（--live 模式）
    # 健壮性：display 不应因 UI/回调异常而打断主流程
    if _ev is not None:
        try:
            _ev("display", display_data)
        except Exception as ex:
            try:
                loop.file_only_logger.warning(f"display 事件回调异常: {ex}", exc_info=True)
            except Exception:
                # 最后兜底：不能让 display 崩溃
                pass
    
    # 6. 降级方案：通过 logger 输出到控制台
    emoji = LEVEL_EMOJI.get(level, "")
    color = LEVEL_COLORS.get(level, "white")
    title_prefix = f"[{title}] " if title else ""
    
    # 截取前 200 字符用于控制台显示
    preview = content[:200] + ("..." if len(content) > 200 else "")
    try:
        loop.logger.info(f"[{color}]{emoji} {title_prefix}{preview}[/{color}]")
    except Exception as ex:
        try:
            loop.file_only_logger.warning(f"display 控制台输出异常: {ex}", exc_info=True)
        except Exception:
            pass
    
    # 7. 记录到审计日志
    if trace_id:
        try:
            loop.audit.write(
                trace_id=trace_id,
                event="display",
                data=display_data,
            )
        except Exception as ex:
            try:
                loop.file_only_logger.warning(f"display 审计写入异常: {ex}", exc_info=True)
            except Exception:
                pass
    
    # 8. 返回成功结果
    _logger.info(f"[Display] 消息显示成功: level={level}, length={len(content)}, truncated={truncated}")
    return ToolResult(
        ok=True,
        payload={
            "displayed": True,
            "length": len(content),
            "level": level,
            "truncated": truncated,
        },
    )

