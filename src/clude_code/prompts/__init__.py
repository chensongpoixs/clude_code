"""
集中管理"发给大模型的提示词（prompt）"。

功能：
- read_prompt: 读取 prompt 文件
- render_prompt: 渲染 prompt 模板（支持 Jinja2）
- load_prompt_asset: 加载完整 prompt 资产（含元数据）
- render_system_prompt: 组合渲染四层 System Prompt
- list_prompt_versions: 列出可用版本

对齐 agent_design_v_1.0.md 设计规范。
"""

from .loader import (
    read_prompt,
    render_prompt,
    load_prompt_asset,
    render_system_prompt,
    list_prompt_versions,
    PromptAsset,
    PromptMetadata,
    JINJA2_AVAILABLE,
)

__all__ = [
    "read_prompt",
    "render_prompt",
    "load_prompt_asset",
    "render_system_prompt",
    "list_prompt_versions",
    "PromptAsset",
    "PromptMetadata",
    "JINJA2_AVAILABLE",
]
