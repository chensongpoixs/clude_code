from __future__ import annotations

from pathlib import Path

from ..types import ToolResult
from ..workspace import resolve_in_workspace


def write_file(*, workspace_root: Path, path: str, text: str, content_based: bool = False, insert_at_line: int | None = None) -> ToolResult:
    p = resolve_in_workspace(workspace_root, path)
    p.parent.mkdir(parents=True, exist_ok=True)

    # 处理不同的写入模式
    if insert_at_line is not None:
        # 指定行插入模式
        if p.exists():
            try:
                existing_content = p.read_text(encoding="utf-8", errors="replace")
                lines = existing_content.splitlines(keepends=True)

                # 确保行号有效
                if insert_at_line < 0:
                    insert_at_line = 0
                elif insert_at_line > len(lines):
                    insert_at_line = len(lines)

                # 在指定行插入内容
                lines.insert(insert_at_line, text)
                final_content = ''.join(lines)
                action = f"inserted_at_line_{insert_at_line}"

            except (OSError, UnicodeDecodeError):
                # 如果读取失败，当作新文件处理
                final_content = text
                action = "wrote"
        else:
            # 文件不存在，直接写入
            final_content = text
            action = "wrote"

    elif content_based and p.exists():
        # 基于内容智能模式
        try:
            existing_content = p.read_text(encoding="utf-8", errors="replace")

            # 如果现有内容为空，直接写入
            if not existing_content.strip():
                final_content = text
                action = "wrote"
            # 如果现有内容不为空，追加新内容
            else:
                final_content = existing_content + text
                action = "appended"
        except (OSError, UnicodeDecodeError):
            # 如果读取失败，当作新文件处理
            final_content = text
            action = "wrote"
    else:
        # 默认行为：直接写入（覆盖）
        final_content = text
        action = "wrote"

    p.write_text(final_content, encoding="utf-8")
    return ToolResult(True, payload={
        "path": path,
        "bytes_written": len(final_content.encode("utf-8")),
        "action": action
    })


