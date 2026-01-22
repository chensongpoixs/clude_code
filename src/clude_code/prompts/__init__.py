"""
集中管理“发给大模型的提示词（prompt）”。

注意：本包只负责存放与加载提示词，不包含业务逻辑。
"""

from .loader import read_prompt, render_prompt
from .prompt_manager import PromptManager, PromptArtifact

__all__ = ["read_prompt", "render_prompt", "PromptManager", "PromptArtifact"]


