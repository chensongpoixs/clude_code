from __future__ import annotations

from pathlib import Path

from .types import ToolError, ToolResult
from .workspace import resolve_in_workspace as _resolve_in_workspace
from .tools.glob_search import glob_file_search as _glob_file_search_impl
from .tools.grep import grep as _grep_impl
from .tools.list_dir import list_dir as _list_dir_impl
from .tools.patching import apply_patch as _apply_patch_impl
from .tools.patching import undo_patch as _undo_patch_impl
from .tools.question import ask_question as _ask_question_impl
from .tools.read_file import read_file as _read_file_impl
from .tools.repo_map import generate_repo_map as _generate_repo_map_impl
from .tools.run_cmd import run_cmd as _run_cmd_impl
from .tools.search import websearch as _websearch_impl, codesearch as _codesearch_impl
from .tools.skill import load_skill as _load_skill_impl, list_skills as _list_skills_impl
from .tools.task_agent import run_task as _run_task_impl, get_task_status as _get_task_status_impl
from .tools.todo_manager import todowrite as _todowrite_impl, todoread as _todoread_impl
from .tools.weather import get_weather as _get_weather_impl, get_weather_forecast as _get_weather_forecast_impl
from .tools.webfetch import fetch_web_content as _fetch_web_content_impl
from .tools.write_file import write_file as _write_file_impl


class LocalTools:
    def __init__(self, workspace_root: str, *, max_file_read_bytes: int, max_output_bytes: int) -> None:
        self.workspace_root = Path(workspace_root)
        self.max_file_read_bytes = max_file_read_bytes
        self.max_output_bytes = max_output_bytes

    def list_dir(self, path: str = ".") -> ToolResult:
        return _list_dir_impl(workspace_root=self.workspace_root, path=path)

    def read_file(self, path: str, offset: int | None = None, limit: int | None = None) -> ToolResult:
        return _read_file_impl(
            workspace_root=self.workspace_root,
            max_file_read_bytes=self.max_file_read_bytes,
            path=path,
            offset=offset,
            limit=limit,
        )

    def write_file(self, path: str, text: str, content_based: bool = False, insert_at_line: int | None = None) -> ToolResult:
        return _write_file_impl(workspace_root=self.workspace_root, path=path, text=text, content_based=content_based, insert_at_line=insert_at_line)

    def apply_patch(
        self,
        path: str,
        old: str,
        new: str,
        expected_replacements: int = 1,
        fuzzy: bool = False,
        min_similarity: float = 0.92,
    ) -> ToolResult:
        return _apply_patch_impl(
            workspace_root=self.workspace_root,
            path=path,
            old=old,
            new=new,
            expected_replacements=expected_replacements,
            fuzzy=fuzzy,
            min_similarity=min_similarity,
        )

    def undo_patch(self, undo_id: str, force: bool = False) -> ToolResult:
        return _undo_patch_impl(workspace_root=self.workspace_root, undo_id=undo_id, force=force)

    def glob_file_search(self, glob_pattern: str, target_directory: str = ".") -> ToolResult:
        return _glob_file_search_impl(workspace_root=self.workspace_root, glob_pattern=glob_pattern, target_directory=target_directory)

    """
    @author: clude_code
    @date: 2026-01-20
    
    Tool: grep（只读；优先 rg）。
    用于在工作区内按正则搜索文本内容（Grep / Ripgrep）。
    支持 C/C++/Java 等多种语言的自动后缀匹配
    如果你在寻找特定语言的定义（如 C++ 类或 Java 方法），指定 'language' 参数将极大提高准确率。
    参数：
    - pattern: 正则表达式模式
    - path: 搜索路径
    - language: 指定语言类型（如 "c++", "java"），用于自动匹配文件后缀
    - include_glob: 额外的 glob 模式，用于进一步限定搜索文件
    - ignore_case: 是否忽略大小写
    - max_hits: 最大返回命中数
    返回： ToolResult，包含匹配结果列表

    """
    def grep(self, pattern: str, path: str = ".", language: str = "all", include_glob: str | None = None, ignore_case: bool = False, max_hits: int = 200) -> ToolResult:
        return _grep_impl(workspace_root=self.workspace_root, pattern=pattern, path=path, language=language, include_glob=include_glob, ignore_case=ignore_case, max_hits=max_hits)

    def generate_repo_map(self) -> str:
        return _generate_repo_map_impl(workspace_root=self.workspace_root)

    def run_cmd(self, command: str, cwd: str = ".", timeout_s: int | None = None) -> ToolResult:
        return _run_cmd_impl(
            workspace_root=self.workspace_root,
            max_output_bytes=self.max_output_bytes,
            command=command,
            cwd=cwd,
            timeout_s=timeout_s,
        )

    def ask_question(self, question: str, options: list[str] | None = None, multiple: bool = False, header: str | None = None) -> ToolResult:
        return _ask_question_impl(question=question, options=options, multiple=multiple, header=header)

    def fetch_web_content(self, url: str, format: str = "markdown", timeout: int = 30, use_cache: bool = True, force_refresh: bool = False) -> ToolResult:
        return _fetch_web_content_impl(url=url, format=format, timeout=timeout, workspace_root=str(self.workspace_root), use_cache=use_cache, force_refresh=force_refresh)

    def websearch(self, query: str, num_results: int = 8, livecrawl: str = "fallback", search_type: str = "auto", context_max_chars: int = 10000) -> ToolResult:
        return _websearch_impl(query=query, num_results=num_results, livecrawl=livecrawl, search_type=search_type, context_max_chars=context_max_chars)

    def codesearch(self, query: str, tokens_num: int = 5000) -> ToolResult:
        return _codesearch_impl(query=query, tokens_num=tokens_num)

    def load_skill(self, skill_name: str) -> ToolResult:
        return _load_skill_impl(skill_name=skill_name, workspace_root=str(self.workspace_root))

    def list_skills(self) -> ToolResult:
        return _list_skills_impl(workspace_root=str(self.workspace_root))

    def todowrite(self, content: str, priority: str = "medium", status: str = "pending") -> ToolResult:
        return _todowrite_impl(content=content, priority=priority, status=status)

    def todoread(self, status: str | None = None, todo_id: str | None = None) -> ToolResult:
        return _todoread_impl(status=status, todo_id=todo_id)

    def run_task(self, description: str, prompt: str, subagent_type: str = "general", session_id: str | None = None) -> ToolResult:
        return _run_task_impl(description=description, prompt=prompt, subagent_type=subagent_type, session_id=session_id)

    def get_task_status(self, task_id: str) -> ToolResult:
        return _get_task_status_impl(task_id=task_id)

    def get_weather(
        self,
        city: str | None = None,
        lat: float | None = None,
        lon: float | None = None,
        units: str = "metric",
        lang: str = "zh_cn",
        timeout: int = 10,
    ) -> ToolResult:
        """获取实时天气信息"""
        return _get_weather_impl(city=city, lat=lat, lon=lon, units=units, lang=lang, timeout=timeout)

    def get_weather_forecast(
        self,
        city: str | None = None,
        lat: float | None = None,
        lon: float | None = None,
        units: str = "metric",
        lang: str = "zh_cn",
        days: int = 5,
        timeout: int = 10,
    ) -> ToolResult:
        """获取天气预报（5天）"""
        return _get_weather_forecast_impl(city=city, lat=lat, lon=lon, units=units, lang=lang, days=days, timeout=timeout)



