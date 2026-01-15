"""
Skill tool - 技能加载工具

加载和执行预定义的技能（SKILL.md文件），提供特定领域的专业知识和操作指导。
"""
from __future__ import annotations

import os
import json
from pathlib import Path
from typing import Any, Dict, Optional

from clude_code.tooling.types import ToolResult, ToolError


def load_skill(
    skill_name: str,
    workspace_root: str
) -> ToolResult:
    """
    加载技能工具

    Args:
        skill_name: 技能名称（文件名，不含扩展名）
        workspace_root: 工作区根目录

    Returns:
        ToolResult: 技能内容
    """
    try:
        # 构建技能文件路径
        skill_file = Path(workspace_root) / f"{skill_name}.md"

        # 检查文件是否存在
        if not skill_file.exists():
            return ToolResult(
                ok=False,
                error={
                    "message": f"Skill file '{skill_file}' not found",
                    "code": "SKILL_NOT_FOUND"
                }
            )

        # 读取技能文件内容
        with open(skill_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # 解析技能元数据（如果有）
        metadata = {}
        lines = content.split('\n')
        if lines and lines[0].startswith('---'):
            # 查找结束标记
            end_idx = -1
            for i, line in enumerate(lines[1:], 1):
                if line.startswith('---'):
                    end_idx = i
                    break

            if end_idx > 0:
                try:
                    metadata_content = '\n'.join(lines[1:end_idx])
                    metadata = json.loads(metadata_content)
                    content = '\n'.join(lines[end_idx + 1:])
                except json.JSONDecodeError:
                    pass  # 元数据不是JSON，保持原样

        result_data = {
            "skill_name": skill_name,
            "file_path": str(skill_file),
            "content": content,
            "metadata": metadata,
            "size": len(content)
        }

        return ToolResult(
            ok=True,
            payload=result_data
        )

    except PermissionError:
        return ToolResult(
            ok=False,
            error={
                "message": f"Permission denied accessing skill file: {skill_name}",
                "code": "SKILL_PERMISSION_DENIED"
            }
        )
    except Exception as e:
        return ToolResult(
            ok=False,
            error={
                "message": f"Failed to load skill '{skill_name}': {str(e)}",
                "code": "SKILL_LOAD_FAILED"
            }
        )


def list_skills(
    workspace_root: str
) -> ToolResult:
    """
    列出可用技能

    Args:
        workspace_root: 工作区根目录

    Returns:
        ToolResult: 技能列表
    """
    try:
        workspace_path = Path(workspace_root)

        # 查找所有.md文件作为潜在技能
        skills = []
        for md_file in workspace_path.rglob("*.md"):
            if md_file.name.endswith('.md'):
                skill_name = md_file.stem
                relative_path = md_file.relative_to(workspace_path)

                # 读取文件大小和修改时间
                stat = md_file.stat()

                skills.append({
                    "name": skill_name,
                    "file_path": str(relative_path),
                    "size": stat.st_size,
                    "modified": stat.st_mtime
                })

        return ToolResult(
            ok=True,
            payload={
                "skills": skills,
                "count": len(skills),
                "workspace": workspace_root
            }
        )

    except Exception as e:
        return ToolResult(
            ok=False,
            error={
                "message": f"Failed to list skills: {str(e)}",
                "code": "SKILL_LIST_FAILED"
            }
        )