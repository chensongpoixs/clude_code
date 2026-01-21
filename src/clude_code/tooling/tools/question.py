"""
Question tool - 向用户提问并获取回答

允许AI在执行过程中向用户提问，收集反馈或澄清需求。
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from clude_code.tooling.types import ToolResult, ToolError
from ..logger_helper import get_tool_logger
from ...config.tools_config import get_question_config

# 工具模块 logger（延迟初始化）
_logger = get_tool_logger(__name__)

"""
向用户提问工具

Args:
    question: 问题文本
    options: 可选的选项列表
    multiple: 是否允许多选
    header: 问题标题

Returns:
    ToolResult: 包含用户回答的工具结果
"""
def ask_question(
    question: str,
    options: Optional[List[str]] = None,
    multiple: bool = False,
    header: Optional[str] = None
) -> ToolResult:

    try:
        # 检查工具是否启用
        config = get_question_config()
        if not config.enabled:
            _logger.warning("[Question] 提问工具已被禁用")
            return ToolResult(False, error={"code": "E_TOOL_DISABLED", "message": "question tool is disabled"})

        _logger.debug(f"[Question] 开始提问: question={question[:50]}..., options={len(options) if options else 0}, multiple={multiple}")
        # 构建问题结构
        question_data = {
            "question": question,
            "header": header or "Question",
            "options": options or [],
            "multiple": multiple
        }

        # 在实际实现中，这里会通过UI/API向用户显示问题并获取回答
        # 现在返回结构化的数据供框架处理

        result_data = {
            "type": "question",
            "data": question_data,
            "status": "pending"  # 等待用户回答
        }

        _logger.info(f"[Question] 问题已创建: status=pending, options={len(options) if options else 0}")
        return ToolResult(
            ok=True,
            payload=result_data
        )

    except Exception as e:
        _logger.error(f"[Question] 提问失败: {e}", exc_info=True)
        return ToolResult(
            ok=False,
            error={
                "message": f"Failed to ask question: {str(e)}",
                "code": "QUESTION_FAILED"
            }
        )