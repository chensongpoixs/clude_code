"""
analyze_image 工具 - 加载并分析图片

让 LLM 可以主动读取和分析图片内容。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..types import ToolResult
from ..logger_helper import get_tool_logger
from clude_code.llm.image_utils import load_image_from_path, load_image_from_url

_logger = get_tool_logger(__name__)


def analyze_image(
    *,
    path: str,
    question: str = "请描述这张图片的内容",
) -> ToolResult:
    """
    加载并准备图片数据用于 LLM 分析。
    
    Args:
        path: 图片路径（本地路径或 URL）
        question: 对图片的提问（会包含在返回中供 LLM 参考）
    
    Returns:
        ToolResult: 包含图片数据（Base64）和问题的结果
    """
    _logger.info(f"[AnalyzeImage] 加载图片: {path}")
    
    # 判断是 URL 还是本地路径
    if path.startswith(('http://', 'https://')):
        img_data = load_image_from_url(path)
    else:
        img_data = load_image_from_path(path)
    
    if not img_data:
        _logger.warning(f"[AnalyzeImage] 无法加载图片: {path}")
        return ToolResult(
            ok=False,
            error={
                "code": "E_IMAGE_LOAD_FAILED",
                "message": f"无法加载图片: {path}",
            }
        )
    
    _logger.info(f"[AnalyzeImage] 图片加载成功: {path}")
    
    # 返回图片数据和问题
    # 注意：图片数据会作为 multimodal content 回喂给 LLM
    return ToolResult(
        ok=True,
        payload={
            "path": path,
            "question": question,
            "image": img_data,  # OpenAI Vision API 格式
            "hint": "请根据图片内容回答问题",
        }
    )

