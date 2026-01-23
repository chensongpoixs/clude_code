"""
工具结果分层压缩模块

实现三层压缩策略：summary → snippet → full
根据工具类型和结果大小智能选择返回级别。

业界对标：
- Claude Code: 分层返回策略
- Cursor: 智能截断 + 关键信息提取
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


# ============================================================
# 压缩结果数据结构
# ============================================================

@dataclass
class CompressedResult:
    """压缩后的工具结果"""
    ok: bool
    summary: str                      # 状态摘要（~20 tokens）
    snippet: str | None = None        # 关键片段（~100 tokens）
    full_available: bool = False      # 是否有完整结果可用
    truncated: bool = False           # 是否被截断
    original_size: int = 0            # 原始大小（字符数）
    compressed_size: int = 0          # 压缩后大小
    
    def to_feedback(self, include_full: bool = False) -> str:
        """生成反馈文本"""
        parts = [f"[{('✓' if self.ok else '✗')}] {self.summary}"]
        
        if self.snippet:
            parts.append(self.snippet)
        
        if self.truncated:
            parts.append(f"(已截断，原始 {self.original_size} 字符)")
        
        return "\n".join(parts)


# ============================================================
# 压缩策略配置
# ============================================================

@dataclass
class CompressionConfig:
    """压缩策略配置"""
    # grep 配置
    grep_snippet_lines: int = 5       # snippet 显示行数
    grep_full_threshold: int = 10     # 超过此数量则截断
    
    # read_file 配置
    read_snippet_lines: int = 50      # snippet 显示行数
    read_full_threshold: int = 200    # 超过此行数则截断
    
    # list_dir 配置
    list_snippet_items: int = 15      # snippet 显示项数
    list_full_threshold: int = 30     # 超过此数量则截断
    
    # run_cmd 配置
    cmd_snippet_lines: int = 20       # snippet 显示行数
    cmd_full_threshold: int = 50      # 超过此行数则截断
    
    # 通用配置
    max_snippet_chars: int = 1500     # snippet 最大字符数
    max_summary_chars: int = 100      # summary 最大字符数


# 默认配置
DEFAULT_CONFIG = CompressionConfig()


# ============================================================
# 工具结果压缩器
# ============================================================

class ResultCompressor:
    """工具结果压缩器"""
    
    def __init__(self, config: CompressionConfig | None = None):
        self.config = config or DEFAULT_CONFIG
    
    def compress(self, tool_name: str, result: dict[str, Any]) -> CompressedResult:
        """
        压缩工具结果。
        
        Args:
            tool_name: 工具名称
            result: 原始工具结果 (ToolResult.payload 或 error)
        
        Returns:
            CompressedResult
        """
        # 分发到具体压缩方法
        compressor = getattr(self, f"_compress_{tool_name}", self._compress_generic)
        return compressor(result)
    
    def _compress_grep(self, result: dict[str, Any]) -> CompressedResult:
        """压缩 grep 结果"""
        ok = result.get("ok", True)
        payload = result.get("payload", {})
        error = result.get("error", {})
        
        if not ok:
            return CompressedResult(
                ok=False,
                summary=f"搜索失败: {error.get('message', '未知错误')}"
            )
        
        hits = payload.get("hits", [])
        total = payload.get("total", len(hits))
        files = set(h.get("file", "") for h in hits if h.get("file"))
        
        summary = f"找到 {total} 个匹配 (涉及 {len(files)} 个文件)"
        
        # 生成 snippet
        snippet_lines = []
        for h in hits[:self.config.grep_snippet_lines]:
            file = h.get("file", "?")
            line = h.get("line", "?")
            text = h.get("text", "")[:80]  # 截断长行
            snippet_lines.append(f"  {file}:{line}: {text}")
        
        if total > self.config.grep_snippet_lines:
            snippet_lines.append(f"  ... 还有 {total - self.config.grep_snippet_lines} 条")
        
        snippet = "\n".join(snippet_lines) if snippet_lines else None
        
        original = json.dumps(payload, ensure_ascii=False)
        return CompressedResult(
            ok=True,
            summary=summary,
            snippet=snippet,
            full_available=total > self.config.grep_full_threshold,
            truncated=total > self.config.grep_full_threshold,
            original_size=len(original),
            compressed_size=len(summary) + (len(snippet) if snippet else 0)
        )
    
    def _compress_read_file(self, result: dict[str, Any]) -> CompressedResult:
        """压缩 read_file 结果"""
        ok = result.get("ok", True)
        payload = result.get("payload", {})
        error = result.get("error", {})
        
        if not ok:
            return CompressedResult(
                ok=False,
                summary=f"读取失败: {error.get('message', '未知错误')}"
            )
        
        content = payload.get("content", "")
        lines = content.split("\n")
        total_lines = len(lines)
        total_chars = len(content)
        
        summary = f"读取 {total_lines} 行 ({total_chars} 字符)"
        
        # 生成 snippet
        truncated = total_lines > self.config.read_snippet_lines
        snippet_lines = lines[:self.config.read_snippet_lines]
        snippet = "\n".join(snippet_lines)
        
        if len(snippet) > self.config.max_snippet_chars:
            snippet = snippet[:self.config.max_snippet_chars] + "\n..."
            truncated = True
        
        if truncated:
            snippet += f"\n... (共 {total_lines} 行)"
        
        return CompressedResult(
            ok=True,
            summary=summary,
            snippet=snippet,
            full_available=truncated,
            truncated=truncated,
            original_size=total_chars,
            compressed_size=len(summary) + len(snippet)
        )
    
    def _compress_list_dir(self, result: dict[str, Any]) -> CompressedResult:
        """压缩 list_dir 结果"""
        ok = result.get("ok", True)
        payload = result.get("payload", {})
        error = result.get("error", {})
        
        if not ok:
            return CompressedResult(
                ok=False,
                summary=f"列出失败: {error.get('message', '未知错误')}"
            )
        
        entries = payload.get("entries", [])
        files = [e for e in entries if e.get("type") == "file"]
        dirs = [e for e in entries if e.get("type") == "dir"]
        
        summary = f"{len(files)} 个文件, {len(dirs)} 个目录"
        
        # 生成 snippet
        snippet_items = []
        for e in entries[:self.config.list_snippet_items]:
            icon = "📁" if e.get("type") == "dir" else "📄"
            name = e.get("name", "?")
            snippet_items.append(f"  {icon} {name}")
        
        if len(entries) > self.config.list_snippet_items:
            snippet_items.append(f"  ... 还有 {len(entries) - self.config.list_snippet_items} 项")
        
        snippet = "\n".join(snippet_items) if snippet_items else None
        
        return CompressedResult(
            ok=True,
            summary=summary,
            snippet=snippet,
            full_available=len(entries) > self.config.list_full_threshold,
            truncated=len(entries) > self.config.list_full_threshold,
            original_size=len(json.dumps(payload, ensure_ascii=False)),
            compressed_size=len(summary) + (len(snippet) if snippet else 0)
        )
    
    def _compress_run_cmd(self, result: dict[str, Any]) -> CompressedResult:
        """压缩 run_cmd 结果"""
        ok = result.get("ok", True)
        payload = result.get("payload", {})
        error = result.get("error", {})
        
        if not ok:
            return CompressedResult(
                ok=False,
                summary=f"执行失败: {error.get('message', '未知错误')}"
            )
        
        exit_code = payload.get("exit_code", 0)
        stdout = payload.get("stdout", "")
        stderr = payload.get("stderr", "")
        output = stdout + stderr
        
        lines = output.split("\n")
        total_lines = len(lines)
        
        status = "成功" if exit_code == 0 else f"失败(退出码{exit_code})"
        summary = f"{status}, 输出 {total_lines} 行 ({len(output)} 字符)"
        
        # 生成 snippet
        truncated = total_lines > self.config.cmd_snippet_lines
        snippet_lines = lines[:self.config.cmd_snippet_lines]
        snippet = "\n".join(snippet_lines)
        
        if len(snippet) > self.config.max_snippet_chars:
            snippet = snippet[:self.config.max_snippet_chars]
            truncated = True
        
        if truncated:
            snippet += f"\n... (共 {total_lines} 行)"
        
        return CompressedResult(
            ok=ok,
            summary=summary,
            snippet=snippet if output.strip() else None,
            full_available=truncated,
            truncated=truncated,
            original_size=len(output),
            compressed_size=len(summary) + (len(snippet) if snippet else 0)
        )
    
    def _compress_apply_patch(self, result: dict[str, Any]) -> CompressedResult:
        """压缩 apply_patch 结果"""
        ok = result.get("ok", True)
        payload = result.get("payload", {})
        error = result.get("error", {})
        
        if not ok:
            return CompressedResult(
                ok=False,
                summary=f"补丁失败: {error.get('message', '未知错误')}"
            )
        
        replacements = payload.get("replacements", 1)
        path = payload.get("path", "?")
        undo_id = payload.get("undo_id", "")
        
        summary = f"成功替换 {replacements} 处 @ {path}"
        snippet = f"  undo_id: {undo_id}" if undo_id else None
        
        return CompressedResult(
            ok=True,
            summary=summary,
            snippet=snippet,
            full_available=False,
            truncated=False,
            original_size=len(json.dumps(payload, ensure_ascii=False)),
            compressed_size=len(summary) + (len(snippet) if snippet else 0)
        )
    
    def _compress_generic(self, result: dict[str, Any]) -> CompressedResult:
        """通用压缩策略"""
        ok = result.get("ok", True)
        payload = result.get("payload", {})
        error = result.get("error", {})
        
        if not ok:
            return CompressedResult(
                ok=False,
                summary=f"失败: {error.get('message', '未知错误')}"
            )
        
        # 通用摘要
        if isinstance(payload, dict):
            keys = list(payload.keys())[:3]
            summary = f"返回 {len(payload)} 个字段 ({', '.join(keys)}...)"
        elif isinstance(payload, list):
            summary = f"返回 {len(payload)} 项"
        else:
            summary = f"返回 {type(payload).__name__}"
        
        # 通用 snippet
        payload_str = json.dumps(payload, ensure_ascii=False, indent=2)
        truncated = len(payload_str) > self.config.max_snippet_chars
        snippet = payload_str[:self.config.max_snippet_chars]
        if truncated:
            snippet += "\n..."
        
        return CompressedResult(
            ok=True,
            summary=summary,
            snippet=snippet,
            full_available=truncated,
            truncated=truncated,
            original_size=len(payload_str),
            compressed_size=len(summary) + len(snippet)
        )


# 单例实例
_compressor: ResultCompressor | None = None


def get_compressor(config: CompressionConfig | None = None) -> ResultCompressor:
    """获取压缩器实例"""
    global _compressor
    if _compressor is None or config is not None:
        _compressor = ResultCompressor(config)
    return _compressor


def compress_tool_result(tool_name: str, result: dict[str, Any]) -> CompressedResult:
    """便捷函数：压缩工具结果"""
    return get_compressor().compress(tool_name, result)

