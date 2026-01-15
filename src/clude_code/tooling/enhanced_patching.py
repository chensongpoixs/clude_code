"""
增强的代码编辑系统
参考Claude Code，实现更精确的patch、diff和编辑操作
"""
import difflib
import re
from typing import List, Tuple, Dict, Any, Optional
from pathlib import Path
from dataclasses import dataclass


@dataclass
class EditLocation:
    """编辑位置信息"""
    start_line: int
    end_line: int
    start_col: int = 0
    end_col: int = 0
    content: str = ""


@dataclass
class EditOperation:
    """编辑操作"""
    operation_type: str  # "replace", "insert", "delete"
    location: EditLocation
    old_content: str
    new_content: str
    confidence: float = 1.0


class EnhancedPatchEngine:
    """
    增强的patch引擎
    参考Claude Code，提供更精确的代码编辑能力
    """

    def __init__(self):
        self.max_context_lines = 5
        self.min_match_length = 10

    def apply_patch_with_context(
        self,
        file_path: Path,
        old_string: str,
        new_string: str,
        context_lines: int = 3
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        使用上下文信息的精确patch应用

        Args:
            file_path: 文件路径
            old_string: 要替换的旧字符串
            new_string: 替换成的新字符串
            context_lines: 上下文行数

        Returns:
            (成功, 错误消息, 详细信息)
        """
        try:
            if not file_path.exists():
                return False, f"文件不存在: {file_path}", {}

            content = file_path.read_text(encoding='utf-8')

            # 查找最佳匹配位置
            locations = self._find_best_matches(content, old_string, context_lines)

            if not locations:
                return False, "未找到匹配的内容", {}

            # 选择最佳匹配
            best_location = max(locations, key=lambda x: x['similarity'])

            if best_location['similarity'] < 0.8:
                return False, f"匹配相似度太低: {best_location['similarity']:.2f}", {}

            # 应用替换
            start_pos = best_location['start_pos']
            end_pos = best_location['end_pos']

            new_content = content[:start_pos] + new_string + content[end_pos:]

            # 验证替换结果
            if old_string in new_content:
                return False, "替换验证失败", {}

            file_path.write_text(new_content, encoding='utf-8')

            return True, "", {
                'similarity': best_location['similarity'],
                'start_line': best_location['start_line'],
                'end_line': best_location['end_line'],
                'context': best_location['context']
            }

        except Exception as e:
            return False, f"patch应用失败: {e}", {}

    def _find_best_matches(
        self,
        content: str,
        target: str,
        context_lines: int
    ) -> List[Dict[str, Any]]:
        """
        查找最佳匹配位置
        """
        lines = content.splitlines()
        target_lines = target.splitlines()
        matches = []

        for i in range(len(lines) - len(target_lines) + 1):
            # 提取候选区域
            candidate_lines = lines[i:i + len(target_lines)]
            candidate = '\n'.join(candidate_lines)

            # 计算相似度
            similarity = self._calculate_similarity(target, candidate)

            if similarity > 0.5:  # 最低相似度阈值
                start_pos = sum(len(lines[j]) + 1 for j in range(i))
                end_pos = start_pos + len(candidate)

                # 提取上下文
                context_start = max(0, i - context_lines)
                context_end = min(len(lines), i + len(target_lines) + context_lines)
                context = '\n'.join(lines[context_start:context_end])

                matches.append({
                    'start_pos': start_pos,
                    'end_pos': end_pos,
                    'start_line': i + 1,
                    'end_line': i + len(target_lines),
                    'similarity': similarity,
                    'context': context
                })

        return matches

    def _calculate_similarity(self, s1: str, s2: str) -> float:
        """计算字符串相似度"""
        return difflib.SequenceMatcher(None, s1, s2).ratio()

    def generate_diff(self, old_content: str, new_content: str) -> str:
        """
        生成统一的diff格式
        """
        old_lines = old_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)

        diff = list(difflib.unified_diff(
            old_lines, new_lines,
            fromfile='old', tofile='new',
            lineterm=''
        ))

        return ''.join(diff)

    def validate_patch(
        self,
        original_content: str,
        old_string: str,
        new_string: str
    ) -> Tuple[bool, str]:
        """
        验证patch的合理性
        """
        # 检查语法一致性
        if old_string.count('{') != old_string.count('}'):
            return False, "旧内容括号不匹配"

        if new_string.count('{') != new_string.count('}'):
            return False, "新内容括号不匹配"

        # 检查缩进一致性
        old_indent = self._get_base_indentation(old_string)
        new_indent = self._get_base_indentation(new_string)

        if abs(len(old_indent) - len(new_indent)) > 4:  # 允许4个字符的差异
            return False, "缩进变化过大，可能导致格式问题"

        return True, ""

    def _get_base_indentation(self, text: str) -> str:
        """获取基础缩进"""
        lines = text.splitlines()
        for line in lines:
            stripped = line.lstrip()
            if stripped:  # 非空行
                return line[:len(line) - len(stripped)]
        return ""

    def create_backup_with_metadata(
        self,
        file_path: Path,
        operation: str,
        metadata: Dict[str, Any]
    ) -> str:
        """
        创建带元数据的备份文件

        Args:
            file_path: 原文件路径
            operation: 操作类型
            metadata: 元数据

        Returns:
            备份文件路径
        """
        import time
        import json
        import hashlib

        timestamp = int(time.time())
        content_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()[:8]

        backup_name = f"{file_path.name}.{operation}.{timestamp}.{content_hash}.bak"
        backup_dir = file_path.parent / ".claude_backups"

        backup_dir.mkdir(exist_ok=True)
        backup_path = backup_dir / backup_name

        # 复制原文件
        import shutil
        shutil.copy2(file_path, backup_path)

        # 保存元数据
        meta_file = backup_path.with_suffix('.meta.json')
        metadata.update({
            'original_file': str(file_path),
            'backup_file': str(backup_path),
            'operation': operation,
            'timestamp': timestamp,
            'content_hash': content_hash,
            'file_size': file_path.stat().st_size
        })

        meta_file.write_text(json.dumps(metadata, indent=2, ensure_ascii=False))

        return str(backup_path)

    def analyze_edit_impact(
        self,
        original_content: str,
        edited_content: str
    ) -> Dict[str, Any]:
        """
        分析编辑的影响
        """
        # 计算基本指标
        original_lines = len(original_content.splitlines())
        edited_lines = len(edited_content.splitlines())

        # 计算diff统计
        diff = list(difflib.unified_diff(
            original_content.splitlines(keepends=True),
            edited_content.splitlines(keepends=True)
        ))

        additions = len([line for line in diff if line.startswith('+')])
        deletions = len([line for line in diff if line.startswith('-')])

        return {
            'original_lines': original_lines,
            'edited_lines': edited_lines,
            'line_difference': edited_lines - original_lines,
            'additions': additions,
            'deletions': deletions,
            'diff_size': len(diff),
            'impact_level': 'high' if additions + deletions > 10 else 'medium' if additions + deletions > 3 else 'low'
        }


# 全局增强patch引擎实例
_enhanced_patch_engine: Optional[EnhancedPatchEngine] = None

def get_enhanced_patch_engine() -> EnhancedPatchEngine:
    """获取增强patch引擎实例"""
    global _enhanced_patch_engine
    if _enhanced_patch_engine is None:
        _enhanced_patch_engine = EnhancedPatchEngine()
    return _enhanced_patch_engine