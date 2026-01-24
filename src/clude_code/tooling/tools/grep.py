"""
Docstring for clude_code.tooling.tools.grep

["rg", "--json"]与 ["rg", "--vimgrep", "--no-heading"]有什么区别呢
这两种格式代表了不同的交互哲学：--json 是给程序（代码）读的，而 --vimgrep 是给人（或模拟人的 LLM）读的


关键         区别                           总结
特性	     --vimgrep	                   --json
主要受众	LLM / 开发者（肉眼）	自动化脚本 / IDE 插件
数据密度	极高（仅包含核心信息）	低（包含大量冗余元数据）
Token 消耗	非常省	非常费
解析难度	简单（字符串切割）	中等（需加载 JSON 库）
匹配细节	仅行号和内容	包含字符精确位移（Offset）

"""


from __future__ import annotations

import re
import shutil
import subprocess
import fnmatch
from pathlib import Path
from typing import Any

from ..types import ToolResult
from ..workspace import resolve_in_workspace
from ..logger_helper import get_tool_logger
from ...config.tools_config import get_search_config

# 工具模块 logger（延迟初始化）
_logger = get_tool_logger(__name__)

# 预览内容最大长度（统一限制，节省 Token）
_MAX_PREVIEW_LENGTH = 200


def _parse_vimgrep_line(line: str) -> dict[str, Any] | None:
    """
    解析 ripgrep --vimgrep 格式的输出行。
    
    格式: file:line:col:content
    Windows 路径示例: C:\path\to\file.cpp:123:4:content
    
    使用正则表达式从右侧解析，处理 Windows 路径中的冒号。
    """
    line = line.rstrip('\n\r')
    if not line:
        return None
    
    # 使用正则表达式匹配：从右侧找到 line:col:content 模式
    # 匹配格式: (\d+):(\d+):(.+)$
    match = re.match(r'^(.+?):(\d+):(\d+):(.+)$', line)
    if match:
        file_path, line_num, col, content = match.groups()
        return {
            "path": file_path,
            "line": int(line_num),
            "preview": content[:_MAX_PREVIEW_LENGTH] + ("..." if len(content) > _MAX_PREVIEW_LENGTH else ""),
        }
    
    # 回退：无列号格式 file:line:content
    match = re.match(r'^(.+?):(\d+):(.+)$', line)
    if match:
        file_path, line_num, content = match.groups()
        return {
            "path": file_path,
            "line": int(line_num),
            "preview": content[:_MAX_PREVIEW_LENGTH] + ("..." if len(content) > _MAX_PREVIEW_LENGTH else ""),
        }
    
    # 最后的回退：简单 split（可能失败，但总比没有好）
    parts = line.rsplit(":", 3)
    if len(parts) >= 4:
        file_path, line_num, col, content = parts[0], parts[1], parts[2], parts[3]
        try:
            return {
                "path": file_path,
                "line": int(line_num) if line_num.isdigit() else 0,
                "preview": content[:_MAX_PREVIEW_LENGTH] + ("..." if len(content) > _MAX_PREVIEW_LENGTH else ""),
            }
        except ValueError:
            return None
    
    return None



def _get_lang_exts(cfg: Any) -> dict[str, list[str]]:
    """从配置获取 language->extensions 映射（并做最小兜底）。"""
    m = getattr(cfg, "grep_language_extensions", None)
    if isinstance(m, dict) and m:
        return {str(k): [str(x) for x in (v or [])] for k, v in m.items() if k}
    return {
        "c": [".c", ".h"],
        "cpp": [".cpp", ".cc", ".cxx", ".h", ".hpp", ".hh"],
        "java": [".java"],
        "python": [".py"],
        "js": [".js", ".jsx", ".ts", ".tsx"],
        "go": [".go"],
        "rust": [".rs"],
    }


def _get_ignore_dirs(cfg: Any) -> set[str]:
    xs = getattr(cfg, "grep_ignore_dirs", []) or []
    return set([str(x) for x in xs if x])


def _get_python_max_file_bytes(cfg: Any) -> int:
    try:
        v = int(getattr(cfg, "grep_python_max_file_bytes", 2_000_000) or 0)
    except Exception:
        v = 2_000_000
    return max(0, v)

"""
优先使用 ripgrep（rg）以获得更稳定性能和结构化输出；无 rg 时回退到 Python 扫描。
大文件治理说明：
- ripgrep 天然高效，且支持排除目录（.git、.clude 等），推荐优先使用。
- Python 扫描时跳过大于 2MB 的  
文件以避免卡顿。
参数说明：
- workspace_root: 工作区根目录
- pattern: 正则表达式模式
- path: 搜索路径
- language: 指定语言类型（如 "c++", "java"），用于自动匹配文件后缀
- include_glob: 额外的包含文件 glob 模式（如 "*.cpp"）
- ignore_case: 是否忽略大小写
- max_hits: 最大返回命中数
返回： ToolResult，包含匹配结果列表
"""
def grep(*, workspace_root: Path, pattern: str, path: str = ".", language: str = "all", include_glob: str | None = None, ignore_case: bool = False, max_hits: int = 200) -> ToolResult:

    # 检查工具是否启用
    config = get_search_config()
    if not config.enabled:
        _logger.warning("[Grep] 搜索工具已被禁用")
        return ToolResult(False, error={"code": "E_TOOL_DISABLED", "message": "search tool is disabled"})

    _logger.debug(f"[Grep] 开始搜索: pattern={pattern}, path={path}, language={language}, include_glob={include_glob}, ignore_case={ignore_case}, max_hits={max_hits}")
    if shutil.which("rg"):
        _logger.debug("[Grep] 使用 ripgrep (rg)")
        tr = _rg_grep(workspace_root=workspace_root, pattern=pattern, path=path, language=language, include_glob=include_glob, ignore_case=ignore_case, max_hits=max_hits, cfg=config)
        if tr.ok:
            _logger.info(f"[Grep] ripgrep 搜索成功: 找到 {len(tr.payload.get('matches', [])) if tr.payload else 0} 个匹配")
            return tr
        _logger.warning("[Grep] ripgrep 搜索失败，回退到 Python 扫描")
    else:
        _logger.debug("[Grep] ripgrep 不可用，使用 Python 扫描")
    return _python_grep(workspace_root=workspace_root, pattern=pattern, path=path, language=language, include_glob=include_glob, ignore_case=ignore_case, max_hits=max_hits, cfg=config)


def old_rg_grep(*, workspace_root: Path, pattern: str, path: str, language: str, include_glob: str | None, ignore_case: bool, max_hits: int) -> ToolResult:
    root = resolve_in_workspace(workspace_root, path)
    if not root.exists():
        _logger.warning(f"[Grep] 搜索路径不存在: {root}");
        return ToolResult(False, error={"code": "E_NOT_FOUND", "message": f"path not found: {path}"})

 

    # 确定要搜索的后缀名集合
    target_exts = set(LANG_EXTENSIONS.get(language, [])) if language != "all" else None



    # try:
    #     cmd = ["rg", "--vimgrep", "--no-heading"]
    #     if ignore_case: cmd.append("-i")
    #     # 默认忽略：降低噪音（尤其是 agent 自己的日志目录）
    #     cmd.extend(["-g", "!.clude/*", "-g", "!.git/*", "-g", "!node_modules/*", "-g", "!.venv/*"])
    #     if target_exts:
    #         for ext in target_exts:
    #             cmd.extend(["-g", f"*{ext}"])

    #     if include_glob:
    #         cmd.extend(["-g", include_glob])
        
    #     cmd.extend([pattern, str(root)]);
        
    #     # 限制返回量，防止进程过载
    #     result = subprocess.run(cmd, 
    #                             capture_output=True, 
    #                             text=True, 
    #                             encoding='utf-8'
    #                             )
    #     if result.stdout:
    #         lines = result.stdout.splitlines()[:max_hits]
    #         return "\n".join(lines)
    # except Exception as e:
    #     return ToolResult(False, error={"code": "E_RG_EXEC", "message": str(e)})


    # 构建 rg 命令行参数
    args = ["rg", "--json"]
    if ignore_case:
        args.append("-i")
    # 默认忽略：降低噪音（尤其是 agent 自己的日志目录）
    args.extend(["-g", "!.clude/*", "-g", "!.git/*", "-g", "!node_modules/*", "-g", "!.venv/*"])

    # 语言特定的文件后缀匹配
    # if language != "all":
    #     lang_suffixes = {
    #         "c++": "*.cpp",
    #         "java": "*.java",
    #         "python": "*.py",
    #         "javascript": "*.js",
    #         "typescript": "*.ts"
    #     }
    #     suffix = lang_suffixes.get(language)
    #     if suffix:
    #         args.extend(["-g", f"{suffix}"])
    if target_exts:
        for ext in target_exts:
            args.extend(["-g", f"*{ext}"])

    # 额外的 glob 模式
    if include_glob:
        args.extend(["-g", include_glob])
    args.append(pattern)
    args.append(path)

    try:
        cp = subprocess.run(
            args,
            cwd=str(workspace_root.resolve()),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
        )
    except Exception as e:
        _logger.error(f"[Grep] rg 执行失败: {e}", exc_info=True);
        return ToolResult(False, error={"code": "E_RG_EXEC", "message": str(e)})

    # rg: returncode=1 表示没匹配，视为 ok
    if cp.returncode not in (0, 1):
        _logger.error(f"[Grep] rg 执行失败: returncode={cp.returncode}, stderr={cp.stderr}");
        return ToolResult(False, error={"code": "E_RG", "message": "rg failed", "details": {"stderr": (cp.stderr or "")}})

    hits: list[dict[str, Any]] = []
    for line in (cp.stdout or "").splitlines():
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict) or obj.get("type") != "match":
            continue
        data = obj.get("data") or {}
        p = (((data.get("path") or {}).get("text")) if isinstance(data.get("path"), dict) else None) or ""
        ln = data.get("line_number") if "line_number" in data else None
        lines = (data.get("lines") or {}).get("text") if isinstance(data.get("lines"), dict) else ""
        hits.append({"path": p, "line": ln, "preview": str(lines)})

    truncated = False
    if len(hits) > max_hits:
        truncated = True
        hits = hits[:max_hits]

    return ToolResult(True, payload={"pattern": pattern, "engine": "rg", "hits": hits, "truncated": truncated})





def _rg_grep(
    *,
    workspace_root: Path,
    pattern: str,
    path: str,
    language: str,
    include_glob: str | None,
    ignore_case: bool,
    max_hits: int,
    cfg: Any,
) -> "ToolResult":
    """
    ripgrep 搜索（优化版：使用 --vimgrep 模式节省 Token）。
    
    --vimgrep 输出格式: file:line:col:content
    相比 --json 节省约 70-80% Token。
    """
    root = resolve_in_workspace(workspace_root, path)
    if not root.exists():
        return ToolResult(False, error={"code": "E_NOT_FOUND", "message": f"path not found: {path}"})

    # 获取语言后缀
    lang_map = _get_lang_exts(cfg)
    target_exts = set(lang_map.get(language, [])) if language != "all" else None

    # 构建 rg 参数 - 使用 vimgrep 模式（Token 优化）
    args = [
        "rg",
        "--vimgrep",       # 输出格式: file:line:col:content（比 --json 省 70%+ Token）
        "--no-heading",    # 不打印文件名标题
        "--color=never",   # 禁用颜色
        "-M", "500",       # 限制每行最大长度（避免超长行刷屏）
    ]
    
    if ignore_case:
        args.append("-i")
    
    # 默认忽略噪音目录（来自配置）
    ignore_dirs = sorted(_get_ignore_dirs(cfg))
    for d in ignore_dirs:
        args.extend(["-g", f"!{d}/*"])

    # 语言后缀匹配
    if target_exts:
        for ext in target_exts:
            args.extend(["-g", f"*{ext}"])

    # 额外 include_glob
    if include_glob:
        args.extend(["-g", include_glob])

    # 搜索模式和路径
    args.append(pattern)
    args.append(str(root))

    try:
        cp = subprocess.Popen(
            args,
            cwd=str(workspace_root.resolve()),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
        )
    except Exception as e:
        return ToolResult(False, error={"code": "E_RG_EXEC", "message": str(e)})

    hits: list[dict[str, Any]] = []
    truncated = False

    # 解析 vimgrep 格式输出（优化版：使用正则表达式处理 Windows 路径）
    if cp.stdout:
        for line in cp.stdout:
            parsed = _parse_vimgrep_line(line)
            if parsed:
                hits.append(parsed)
            
            if len(hits) >= max_hits:
                truncated = True
                # 正确终止进程：先 terminate，再 wait，最后 kill（如果需要）
                cp.terminate()
                try:
                    cp.wait(timeout=1.0)  # 等待进程结束，最多1秒
                except subprocess.TimeoutExpired:
                    cp.kill()  # 强制终止
                    cp.wait()  # 等待 kill 完成
                break

    # 等待进程结束，获取 stderr（如果还没有等待）
    if not truncated:
        _, stderr = cp.communicate()
    else:
        # 如果已经终止，读取剩余 stderr
        try:
            _, stderr = cp.communicate(timeout=0.5)
        except subprocess.TimeoutExpired:
            stderr = ""
    if cp.returncode not in (0, 1):
        return ToolResult(False, error={
            "code": "E_RG",
            "message": "rg failed",
            "details": {"stderr": (stderr or "")}
        })

    return ToolResult(True, payload={"pattern": pattern, "engine": "rg-vimgrep", "hits": hits, "truncated": truncated})

def _python_grep(*, workspace_root: Path, pattern: str, path: str, language: str, include_glob: str | None, ignore_case: bool, max_hits: int, cfg: Any) -> ToolResult:
    root = resolve_in_workspace(workspace_root, path)
    if not root.exists():
        return ToolResult(False, error={"code": "E_NOT_FOUND", "message": f"path not found: {path}"})
    flags = re.IGNORECASE if ignore_case else 0
    try:
        rx = re.compile(pattern, flags)
    except re.error as e:
        return ToolResult(False, error={"code": "E_INVALID_REGEX", "message": str(e)})

    lang_map = _get_lang_exts(cfg)
    target_exts = set(lang_map.get(language, [])) if language != "all" else None
    ignore_dirs = _get_ignore_dirs(cfg)
    max_bytes = _get_python_max_file_bytes(cfg)

    hits: list[dict[str, Any]] = []
    for fp in root.rglob("*"):
        if fp.is_dir():
            continue
        if ignore_dirs and any(part in fp.parts for part in ignore_dirs):
            continue
        if target_exts is not None and fp.suffix.lower() not in target_exts:
            continue
        if include_glob and not fnmatch.fnmatch(fp.name, include_glob):
            continue
        try:
            if max_bytes > 0 and fp.stat().st_size > max_bytes:
                continue
            content = fp.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for i, line in enumerate(content.splitlines(), start=1):
            if rx.search(line):
                rel = str(fp.resolve().relative_to(workspace_root.resolve()))
                # 统一预览长度限制（与 vimgrep 模式一致）
                preview = line[:_MAX_PREVIEW_LENGTH] + ("..." if len(line) > _MAX_PREVIEW_LENGTH else "")
                hits.append({"path": rel, "line": i, "preview": preview})
                if len(hits) >= max_hits:
                    return ToolResult(True, payload={"pattern": pattern, "engine": "python", "hits": hits, "truncated": True})

    return ToolResult(True, payload={"pattern": pattern, "engine": "python", "hits": hits, "truncated": False})


