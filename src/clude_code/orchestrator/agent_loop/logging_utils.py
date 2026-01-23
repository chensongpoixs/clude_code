import json
from typing import Any
from clude_code.tooling.local_tools import ToolResult

def format_args_summary(tool_name: str, args: dict[str, Any]) -> str:
    """
    格式化工具参数摘要（用于日志输出）。
    
    根据工具类型提取关键参数，避免输出过长。
    """
    if tool_name == "read_file":
        path = args.get("path", "")
        offset = args.get("offset")
        limit = args.get("limit")
        parts = [f"path={path}"]
        if offset is not None:
            parts.append(f"offset={offset}")
        if limit is not None:
            parts.append(f"limit={limit}")
        return " ".join(parts)
    elif tool_name == "grep":
        pattern = args.get("pattern", "")[:60]
        path = args.get("path", ".")
        return f"pattern={pattern!r} path={path}"
    elif tool_name == "apply_patch":
        path = args.get("path", "")
        expected = args.get("expected_replacements", 1)
        fuzzy = args.get("fuzzy", False)
        return f"path={path} expected={expected} fuzzy={fuzzy}"
    elif tool_name == "write_file":
        path = args.get("path", "")
        text_len = len(args.get("text", ""))
        return f"path={path} text_len={text_len}"
    elif tool_name == "run_cmd":
        cmd = args.get("command", "")[:100]
        cwd = args.get("cwd", ".")
        return f"cmd={cmd!r} cwd={cwd}"
    elif tool_name == "list_dir":
        path = args.get("path", ".")
        return f"path={path}"
    elif tool_name == "glob_file_search":
        pattern = args.get("glob_pattern", "")
        target = args.get("target_directory", ".")
        return f"pattern={pattern} target={target}"
    else:
        # 通用：只显示前 3 个参数，避免过长
        items = list(args.items())[:3]
        parts = [f"{k}={str(v)[:50]}" for k, v in items]
        if len(args) > 3:
            parts.append("...")
        return " ".join(parts)

def format_result_summary(tool_name: str, result: ToolResult) -> str:
    """
    格式化工具执行结果摘要（用于日志输出）。
    
    根据工具类型和结果提取关键信息，避免输出过长。
    """
    if not result.ok:
        error_msg = result.error.get("message", str(result.error)) if isinstance(result.error, dict) else str(result.error)
        return f"失败: {error_msg[:100]}"
    
    if not result.payload:
        return "成功（无 payload）"
    
    payload = result.payload
    
    if tool_name == "read_file":
        text_len = len(payload.get("text", ""))
        return f"成功: 读取 {text_len} 字符"
    elif tool_name == "grep":
        hits = payload.get("hits", [])
        count = len(hits)
        truncated = payload.get("truncated", False)
        return f"成功: 找到 {count} 个匹配{'（已截断）' if truncated else ''}"
    elif tool_name == "apply_patch":
        replacements = payload.get("replacements", 0)
        undo_id = payload.get("undo_id", "")
        return f"成功: {replacements} 处替换 undo_id={undo_id[:20]}"
    elif tool_name == "write_file":
        return "成功: 文件已写入"
    elif tool_name == "run_cmd":
        exit_code = payload.get("exit_code", -1)
        stdout_len = len(payload.get("stdout", ""))
        stderr_len = len(payload.get("stderr", ""))
        return f"成功: exit_code={exit_code} stdout={stdout_len}字符 stderr={stderr_len}字符"
    elif tool_name == "list_dir":
        items = payload.get("items", [])
        count = len(items)
        return f"成功: {count} 项"
    elif tool_name == "glob_file_search":
        matches = payload.get("matches", [])
        count = len(matches)
        return f"成功: 找到 {count} 个文件"
    elif tool_name == "search_semantic":
        hits = payload.get("hits", [])
        count = len(hits)
        return f"成功: {count} 个语义匹配"
    else:
        # 通用：显示 payload 的键
        keys = list(payload.keys()) if isinstance(payload, dict) else []
        keys_preview = keys[:8]
        more = "…" if len(keys) > len(keys_preview) else ""
        return f"成功: payload_keys={keys_preview}{more}"

