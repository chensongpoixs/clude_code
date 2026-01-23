from __future__ import annotations

from pathlib import Path
from typing import Any

from ..types import ToolResult
from ..workspace import resolve_in_workspace
from ..logger_helper import get_tool_logger
from ...config.tools_config import get_file_config

# 工具模块 logger（延迟初始化）
_logger = get_tool_logger(__name__)


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
) -> ToolResult:
    """
    读取文件（带尺寸上限、编码容错、可选的按行切片）。
    
    优化特性（Phase 2）：
    - 流式读取：大文件只读取需要的部分，内存峰值 ≤ max_bytes * 1.2
    - 智能采样：超大文件采用头尾采样，保留关键信息
    - 行定位：支持 offset/limit 精确定位
    """
    # 检查工具是否启用
    config = get_file_config()
    if not config.enabled:
        _logger.warning("[ReadFile] 文件读取工具已被禁用")
        return ToolResult(False, error={"code": "E_TOOL_DISABLED", "message": "file tool is disabled"})

    try:
        _logger.debug(f"[ReadFile] 开始读取文件: {path}, offset={offset}, limit={limit}")
        p = resolve_in_workspace(workspace_root, path)
        if not p.exists() or not p.is_file():
            _logger.warning(f"[ReadFile] 文件不存在或不是文件: {path}")
            return ToolResult(False, error={"code": "E_NOT_FILE", "message": f"not a file: {path}"})

        file_size = p.stat().st_size
        _logger.debug(f"[ReadFile] 文件大小: {file_size} bytes, 限制: {max_file_read_bytes} bytes")
        
        # 使用流式读取（内存优化）
        text, total_size, truncated, metadata = _read_file_streaming(
            p, max_file_read_bytes, offset, limit
        )
        
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


