from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

from ..types import ToolResult
from ..workspace import resolve_in_workspace
from ..logger_helper import get_tool_logger
from ...config.tools_config import get_file_config

# 工具模块 logger（延迟初始化）
_logger = get_tool_logger(__name__)


def _extract_python_symbol(source: str, symbol: str, skip_docstring: bool = True) -> str | None:
    """
    使用 AST 提取 Python 文件中指定的函数/类定义。
    
    Args:
        source: 源代码
        symbol: 函数名或类名
        skip_docstring: 是否跳过 docstring
    
    Returns:
        提取的代码，或 None（未找到）
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    
    lines = source.splitlines(keepends=True)
    
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name == symbol:
                start_line = node.lineno - 1  # 0-based
                end_line = node.end_lineno or (start_line + 1)
                
                # 提取代码行
                code_lines = lines[start_line:end_line]
                code = "".join(code_lines)
                
                if skip_docstring and node.body:
                    # 检查第一个语句是否是 docstring
                    first = node.body[0]
                    if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                        # 找到 docstring，跳过它
                        docstring_end = first.end_lineno or (first.lineno)
                        # 重新提取，跳过 docstring
                        # 保留函数签名（从 start_line 到 docstring 开始行）
                        sig_end = first.lineno - 1  # docstring 开始行（0-based）
                        remaining_start = docstring_end  # docstring 结束后的行
                        
                        sig_lines = lines[start_line:sig_end]
                        body_lines = lines[remaining_start:end_line]
                        code = "".join(sig_lines) + "        # ... (docstring skipped)\n" + "".join(body_lines)
                
                return code.rstrip()
    
    return None


def _extract_symbol_by_regex(source: str, symbol: str, lang: str) -> str | None:
    """
    使用正则表达式提取非 Python 文件中的函数/类定义。
    
    支持：JavaScript/TypeScript, Go, Rust, C/C++
    """
    patterns = {
        "js": rf"(?:export\s+)?(?:async\s+)?(?:function|const|let|var)\s+{re.escape(symbol)}\s*[=\(].*?(?=\n(?:export\s+)?(?:async\s+)?(?:function|const|let|var)\s+|\n\Z)",
        "ts": rf"(?:export\s+)?(?:async\s+)?(?:function|const|let|var)\s+{re.escape(symbol)}\s*[=\(<].*?(?=\n(?:export\s+)?(?:async\s+)?(?:function|const|let|var)\s+|\n\Z)",
        "go": rf"func\s+(?:\([^)]*\)\s+)?{re.escape(symbol)}\s*\([^)]*\).*?\{{.*?\n\}}",
        "rust": rf"(?:pub\s+)?(?:async\s+)?fn\s+{re.escape(symbol)}\s*[<\(].*?\{{.*?\n\}}",
        "c": rf"(?:\w+\s+)+{re.escape(symbol)}\s*\([^)]*\)\s*\{{.*?\n\}}",
    }
    
    pattern = patterns.get(lang)
    if not pattern:
        return None
    
    match = re.search(pattern, source, re.DOTALL | re.MULTILINE)
    if match:
        return match.group(0)
    
    return None


def _strip_comments(text: str, lang: str) -> str:
    """
    移除代码中的注释（保留功能代码）。
    """
    if lang == "py":
        # Python: 移除 # 注释（但保留字符串中的 #）
        lines = []
        for line in text.splitlines():
            # 简单处理：移除行尾注释
            stripped = line.rstrip()
            # 查找不在字符串中的 #
            in_string = False
            string_char = None
            result = []
            i = 0
            while i < len(stripped):
                c = stripped[i]
                if in_string:
                    result.append(c)
                    if c == string_char and (i == 0 or stripped[i-1] != '\\'):
                        in_string = False
                elif c in '"\'':
                    in_string = True
                    string_char = c
                    result.append(c)
                elif c == '#':
                    # 行尾注释开始
                    break
                else:
                    result.append(c)
                i += 1
            lines.append("".join(result).rstrip())
        return "\n".join(lines)
    
    elif lang in ("js", "ts", "c", "go", "rust"):
        # C-style: 移除 // 和 /* */ 注释
        # 简化处理：只移除 // 注释
        lines = []
        for line in text.splitlines():
            idx = line.find("//")
            if idx >= 0:
                # 检查是否在字符串中（简化：假设不在）
                lines.append(line[:idx].rstrip())
            else:
                lines.append(line)
        return "\n".join(lines)
    
    return text


def _detect_lang(path: str) -> str:
    """根据文件扩展名检测语言类型。"""
    ext = Path(path).suffix.lower()
    lang_map = {
        ".py": "py",
        ".js": "js", ".jsx": "js", ".mjs": "js",
        ".ts": "ts", ".tsx": "ts",
        ".go": "go",
        ".rs": "rust",
        ".c": "c", ".h": "c", ".cpp": "c", ".hpp": "c", ".cc": "c",
    }
    return lang_map.get(ext, "unknown")


def _read_file_streaming(
    file_path: Path,
    max_bytes: int,
    offset: int | None = None,
    limit: int | None = None,
) -> tuple[str, int, bool, dict[str, Any]]:
    """
    流式读取文件（内存优化版本）。
    
    对于大文件，只读取需要的部分，避免内存峰值。
    
    Args:
        file_path: 文件路径
        max_bytes: 最大读取字节数
        offset: 起始行号（1-based）
        limit: 读取行数限制
    
    Returns:
        (text, total_size, truncated, metadata)
    """
    file_size = file_path.stat().st_size
    metadata: dict[str, Any] = {}
    
    # 小文件：直接读取（无需流式）
    if file_size <= max_bytes:
        text = file_path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        
        # 按行切片
        if offset is not None or limit is not None:
            start = max((offset or 1) - 1, 0)
            count = limit or 200
            end = min(start + count, len(lines))
            text = "\n".join(lines[start:end])
            metadata["lines_returned"] = end - start
            metadata["total_lines"] = len(lines)
        
        return text, file_size, False, metadata
    
    # 大文件：流式读取（内存优化）
    _logger.debug(f"[ReadFile] 大文件流式读取: {file_size} bytes > {max_bytes} bytes")
    
    # 使用文件对象分块读取，只读取需要的部分
    with open(file_path, "rb") as f:
        # 计算读取策略
        if offset is not None:
            # 指定了 offset：跳过前面的行，读取指定范围
            # 先统计总行数（快速扫描）
            f.seek(0)
            total_lines = sum(1 for _ in f)
            
            # 定位到指定行
            f.seek(0)
            start = max((offset or 1) - 1, 0)
            count = limit or 200
            
            # 跳过前 start 行
            lines_read = []
            current_line = 0
            bytes_read = 0
            
            for line in f:
                if current_line >= start:
                    if len(lines_read) >= count:
                        break
                    decoded = line.decode("utf-8", errors="replace").rstrip('\n\r')
                    lines_read.append(decoded)
                    bytes_read += len(line)
                    
                    # 防止读取过多
                    if bytes_read > max_bytes:
                        break
                current_line += 1
            
            text = "\n".join(lines_read)
            metadata["lines_returned"] = len(lines_read)
            metadata["total_lines"] = total_lines
            return text, file_size, True, metadata
        
        else:
            # 未指定 offset：头尾采样策略
            # 头部 60%，尾部 40%
            head_bytes = int(max_bytes * 0.6)
            tail_bytes = max_bytes - head_bytes - 100  # 预留空间给省略标记
            
            # 读取头部
            f.seek(0)
            head_data = f.read(head_bytes)
            head_text = head_data.decode("utf-8", errors="replace")
            
            # 确保在完整行结束
            if not head_text.endswith('\n'):
                last_newline = head_text.rfind('\n')
                if last_newline > 0:
                    head_text = head_text[:last_newline + 1]
            
            # 读取尾部
            f.seek(max(0, file_size - tail_bytes))
            tail_data = f.read(tail_bytes)
            tail_text = tail_data.decode("utf-8", errors="replace")
            
            # 确保从完整行开始
            first_newline = tail_text.find('\n')
            if first_newline > 0:
                tail_text = tail_text[first_newline + 1:]
            
            # 计算省略的字节数
            skipped_bytes = file_size - len(head_data) - len(tail_data)
            skipped_kb = skipped_bytes // 1024
            
            # 组合文本
            separator = f"\n\n... [省略中间 {skipped_kb}KB，文件总大小 {file_size // 1024}KB] ...\n\n"
            text = head_text + separator + tail_text
            
            metadata["sampling_mode"] = "head_tail"
            metadata["head_bytes"] = len(head_data)
            metadata["tail_bytes"] = len(tail_data)
            metadata["skipped_bytes"] = skipped_bytes
            
            return text, file_size, True, metadata


def read_file(
    *,
    workspace_root: Path,
    max_file_read_bytes: int,
    path: str,
    offset: int | None = None,
    limit: int | None = None,
    symbol: str | None = None,
    skip_docstring: bool = True,
    skip_comments: bool = False,
) -> ToolResult:
    """
    读取文件（带尺寸上限、编码容错、可选的按行切片或按符号读取）。
    
    优化特性：
    - 流式读取：大文件只读取需要的部分
    - 按符号读取：指定 symbol 参数只读取特定函数/类
    - 跳过注释：skip_docstring=True 跳过 docstring，skip_comments=True 跳过行注释
    
    Args:
        symbol: 函数名或类名（只读取该符号的定义，节省 token）
        skip_docstring: 跳过 docstring（仅对 symbol 模式有效）
        skip_comments: 跳过行注释
    """
    # 检查工具是否启用
    config = get_file_config()
    if not config.enabled:
        _logger.warning("[ReadFile] 文件读取工具已被禁用")
        return ToolResult(False, error={"code": "E_TOOL_DISABLED", "message": "file tool is disabled"})

    try:
        _logger.debug(f"[ReadFile] 开始读取文件: {path}, offset={offset}, limit={limit}, symbol={symbol}")
        p = resolve_in_workspace(workspace_root, path)
        if not p.exists() or not p.is_file():
            _logger.warning(f"[ReadFile] 文件不存在或不是文件: {path}")
            return ToolResult(False, error={"code": "E_NOT_FILE", "message": f"not a file: {path}"})

        file_size = p.stat().st_size
        lang = _detect_lang(path)
        _logger.debug(f"[ReadFile] 文件大小: {file_size} bytes, 语言: {lang}, 限制: {max_file_read_bytes} bytes")
        
        # 按符号读取模式（节省 token）
        if symbol:
            _logger.debug(f"[ReadFile] 按符号读取模式: symbol={symbol}")
            source = p.read_text(encoding="utf-8", errors="replace")
            
            if lang == "py":
                extracted = _extract_python_symbol(source, symbol, skip_docstring=skip_docstring)
            else:
                extracted = _extract_symbol_by_regex(source, symbol, lang)
            
            if extracted is None:
                return ToolResult(False, error={
                    "code": "E_SYMBOL_NOT_FOUND",
                    "message": f"Symbol '{symbol}' not found in {path}"
                })
            
            text = extracted
            if skip_comments:
                text = _strip_comments(text, lang)
            
            return ToolResult(True, payload={
                "path": path,
                "symbol": symbol,
                "total_size": file_size,
                "read_size": len(text.encode("utf-8", errors="ignore")),
                "truncated": False,
                "text": text,
                "mode": "symbol",
                "skip_docstring": skip_docstring,
                "skip_comments": skip_comments,
            })
        
        # 常规读取模式
        # 使用流式读取（内存优化）
        text, total_size, truncated, metadata = _read_file_streaming(
            p, max_file_read_bytes, offset, limit
        )
        
        # 跳过注释（可选）
        if skip_comments and not truncated:
            text = _strip_comments(text, lang)
        
        _logger.debug(f"[ReadFile] 流式读取完成: truncated={truncated}, metadata={metadata}")

        res_payload: dict[str, Any] = {
            "path": path,
            "total_size": total_size,
            "read_size": len(text.encode("utf-8", errors="ignore")),
            "truncated": truncated,
            "text": text,
        }
        
        # 添加元数据
        if metadata:
            res_payload.update(metadata)
        
        if truncated:
            if "sampling_mode" in metadata:
                res_payload["warning"] = (
                    f"File is too large ({total_size} bytes). "
                    f"Using head+tail sampling, skipped {metadata.get('skipped_bytes', 0)} bytes."
                )
            else:
                res_payload["warning"] = (
                    f"File is too large ({total_size} bytes). Output truncated to {max_file_read_bytes} bytes."
                )

        if offset is not None:
            res_payload["offset"] = offset
        if limit is not None:
            res_payload["limit"] = limit
            
        _logger.info(f"[ReadFile] 读取成功: {path}, 返回大小: {res_payload['read_size']} bytes")
        return ToolResult(True, payload=res_payload)
    except Exception as e:
        _logger.error(f"[ReadFile] 读取失败: {path}, 错误: {e}", exc_info=True)
        return ToolResult(False, error={"code": "E_READ", "message": f"读取失败: {path}, 错误: {e}"})


