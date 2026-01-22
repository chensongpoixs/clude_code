"""
AgentLoop prompts helpers

当前版本：system prompt 的拼接与渲染已迁移到 `AgentLoop._build_system_prompt()`，
此模块仅保留“项目记忆读取”等与 prompt 内容无关的辅助函数。
"""


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


