"""
集中管理 AgentLoop 的系统提示词（SYSTEM_PROMPT）。

大文件治理说明：
- 把长字符串/模板从主逻辑文件拆出，避免 `agent_loop.py` 充斥大段文本。
"""

from clude_code.prompts import read_prompt
from .tool_dispatch import render_tools_for_system_prompt


_TOOLS_SECTION = render_tools_for_system_prompt(include_schema=False)


# 新结构：system/core/global.md 为全局规范（对应旧 agent_loop/system_base.md）
_BASE_SYSTEM_PROMPT = read_prompt("system/core/global.md")


# Agent 自己的大模型（保留兼容，内容相同）
_LOCAL_AGENT_RUNTIME_SYSTEM_PROMPT_ = read_prompt("system/core/global.md")


SYSTEM_PROMPT = _BASE_SYSTEM_PROMPT + "\n\n# 可用工具清单\n" + _TOOLS_SECTION + "\n"


def load_project_memory(workspace_root: str) -> tuple[str, dict[str, object]]:
    """
    对标 Claude Code：尝试从工作区根目录读取 CLUDE.md 作为项目记忆/规则。

    兼容性：
    - 优先读取 `CLUDE.md`
    - 若不存在则回退读取旧文件名 `CLAUDE.md`（避免历史项目直接失效）
    """
    from pathlib import Path

    root = Path(workspace_root)
    p = root / "CLUDE.md"
    legacy = False
    if not p.exists():
        legacy_p = root / "CLAUDE.md"
        if legacy_p.exists():
            p = legacy_p
            legacy = True
        else:
            return "", {"loaded": False, "path": str(root / "CLUDE.md"), "length": 0, "truncated": False}

    try:
        content = p.read_text(encoding="utf-8", errors="replace").strip()
        if not content:
            return "", {"loaded": False, "path": str(p), "length": 0, "truncated": False}

        # 护栏：避免把过大的记忆文件塞进 system prompt（token 爆炸）
        max_chars = 20_000
        truncated = False
        if len(content) > max_chars:
            content = content[:max_chars] + "\n...(内容已截断)\n"
            truncated = True

        src_name = "CLAUDE.md" if legacy else "CLUDE.md"
        text = f"\n\n# 项目记忆与自定义规则 (来自 {src_name})\n{content}\n"
        meta: dict[str, object] = {
            "loaded": True,
            "path": str(p),
            "length": len(content),
            "truncated": truncated,
            "legacy_name": legacy,
        }
        return text, meta
    except Exception as e:
        # 读取失败不阻塞主流程
        return "", {"loaded": False, "path": str(p), "length": 0, "truncated": False, "error": str(e), "legacy_name": legacy}


def get_project_memory(workspace_root: str) -> str:
    """
    兼容层：旧函数签名，返回拼接后的文本。
    """
    text, _meta = load_project_memory(workspace_root)
    return text


