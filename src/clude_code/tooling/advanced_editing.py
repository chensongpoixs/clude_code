"""
高级代码编辑功能
参考Claude Code，实现多文件编辑、编辑预览、批量操作等
"""
import asyncio
import hashlib
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor
import difflib


@dataclass
class EditPreview:
    """编辑预览信息"""
    file_path: Path
    old_content: str
    new_content: str
    line_changes: List[Tuple[int, str, str]]  # (line_number, old_line, new_line)
    confidence: float
    impact_level: str  # "low", "medium", "high"


@dataclass
class MultiFileEdit:
    """多文件编辑任务"""
    edits: List[Dict[str, Any]] = field(default_factory=list)
    preview_results: List[EditPreview] = field(default_factory=list)
    execution_order: List[str] = field(default_factory=list)


class AdvancedCodeEditor:
    """
    高级代码编辑器
    参考Claude Code，提供批量编辑、预览、依赖分析等高级功能
    """

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.executor = ThreadPoolExecutor(max_workers=4)

    async def preview_multi_file_edit(self, edits: List[Dict[str, Any]]) -> List[EditPreview]:
        """
        预览多文件编辑的影响

        Args:
            edits: 编辑任务列表，每个包含 path, old_string, new_string 等

        Returns:
            编辑预览列表
        """
        previews = []

        # 并行预览所有编辑
        tasks = []
        for edit in edits:
            task = asyncio.get_event_loop().run_in_executor(
                self.executor, self._preview_single_edit, edit
            )
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                # 处理预览失败的情况
                continue
            if result:
                previews.append(result)

        return previews

    def _preview_single_edit(self, edit: Dict[str, Any]) -> Optional[EditPreview]:
        """
        预览单个编辑
        """
        try:
            file_path = self.workspace_root / edit['path']
            if not file_path.exists():
                return None

            old_content = file_path.read_text(encoding='utf-8')
            old_string = edit.get('old_string', '')
            new_string = edit.get('new_string', '')

            # 生成新内容
            new_content = old_content.replace(old_string, new_string, 1)

            # 分析行级变化
            line_changes = self._analyze_line_changes(old_content, new_content)

            # 计算置信度
            confidence = self._calculate_edit_confidence(old_string, old_content)

            # 评估影响程度
            impact_level = self._assess_edit_impact(line_changes)

            return EditPreview(
                file_path=file_path,
                old_content=old_content,
                new_content=new_content,
                line_changes=line_changes,
                confidence=confidence,
                impact_level=impact_level
            )

        except Exception:
            return None

    def _analyze_line_changes(self, old_content: str, new_content: str) -> List[Tuple[int, str, str]]:
        """
        分析行级变化
        """
        old_lines = old_content.splitlines()
        new_lines = new_content.splitlines()

        changes = []
        max_lines = max(len(old_lines), len(new_lines))

        for i in range(max_lines):
            old_line = old_lines[i] if i < len(old_lines) else ""
            new_line = new_lines[i] if i < len(new_lines) else ""

            if old_line != new_line:
                changes.append((i + 1, old_line, new_line))

        return changes

    def _calculate_edit_confidence(self, old_string: str, content: str) -> float:
        """
        计算编辑置信度
        """
        if old_string in content:
            # 精确匹配
            count = content.count(old_string)
            return 1.0 if count == 1 else 0.8  # 多个匹配降低置信度
        else:
            # 模糊匹配 - 简化计算
            return 0.6

    def _assess_edit_impact(self, line_changes: List[Tuple[int, str, str]]) -> str:
        """
        评估编辑影响程度
        """
        change_count = len(line_changes)

        if change_count == 0:
            return "none"
        elif change_count <= 2:
            return "low"
        elif change_count <= 10:
            return "medium"
        else:
            return "high"

    async def apply_multi_file_edit(self, edits: List[Dict[str, Any]],
                                   dry_run: bool = False) -> Dict[str, Any]:
        """
        应用多文件编辑

        Args:
            edits: 编辑任务列表
            dry_run: 是否仅预览不执行

        Returns:
            执行结果
        """
        # 首先预览所有编辑
        previews = await self.preview_multi_file_edit(edits)

        if dry_run:
            return {
                "success": True,
                "dry_run": True,
                "previews": [self._preview_to_dict(p) for p in previews]
            }

        # 按依赖顺序排序编辑
        ordered_edits = self._sort_edits_by_dependencies(edits, previews)

        # 依次应用编辑
        results = []
        for edit in ordered_edits:
            result = self._apply_single_edit(edit)
            results.append(result)

            # 如果有失败，停止执行
            if not result['success']:
                break

        return {
            "success": all(r['success'] for r in results),
            "results": results,
            "previews": [self._preview_to_dict(p) for p in previews]
        }

    def _sort_edits_by_dependencies(self, edits: List[Dict[str, Any]],
                                   previews: List[EditPreview]) -> List[Dict[str, Any]]:
        """
        根据依赖关系排序编辑
        """
        # 简化实现：按文件路径排序
        return sorted(edits, key=lambda e: e['path'])

    def _apply_single_edit(self, edit: Dict[str, Any]) -> Dict[str, Any]:
        """
        应用单个编辑
        """
        try:
            from clude_code.tooling.tools.patching import apply_patch

            result = apply_patch(
                workspace_root=self.workspace_root,
                path=edit['path'],
                old=edit.get('old_string', ''),
                new=edit.get('new_string', ''),
                expected_replacements=1
            )

            return {
                "success": result.ok,
                "file": edit['path'],
                "error": result.error if not result.ok else None,
                "payload": result.payload if result.ok else None
            }

        except Exception as e:
            return {
                "success": False,
                "file": edit['path'],
                "error": str(e)
            }

    def _preview_to_dict(self, preview: EditPreview) -> Dict[str, Any]:
        """将预览转换为字典"""
        return {
            "file_path": str(preview.file_path),
            "confidence": preview.confidence,
            "impact_level": preview.impact_level,
            "line_changes_count": len(preview.line_changes),
            "content_diff": len(preview.new_content) - len(preview.old_content)
        }

    def generate_edit_summary(self, previews: List[EditPreview]) -> Dict[str, Any]:
        """
        生成编辑摘要
        """
        total_files = len(previews)
        total_changes = sum(len(p.line_changes) for p in previews)
        avg_confidence = sum(p.confidence for p in previews) / total_files if total_files > 0 else 0

        impact_distribution = {}
        for preview in previews:
            impact_distribution[preview.impact_level] = impact_distribution.get(preview.impact_level, 0) + 1

        return {
            "total_files": total_files,
            "total_changes": total_changes,
            "average_confidence": avg_confidence,
            "impact_distribution": impact_distribution,
            "high_impact_files": [str(p.file_path) for p in previews if p.impact_level == "high"]
        }


# 全局高级代码编辑器实例
_advanced_editor: Optional[AdvancedCodeEditor] = None

def get_advanced_code_editor(workspace_root: Path) -> AdvancedCodeEditor:
    """获取高级代码编辑器实例"""
    global _advanced_editor
    if _advanced_editor is None or _advanced_editor.workspace_root != workspace_root:
        _advanced_editor = AdvancedCodeEditor(workspace_root)
    return _advanced_editor