from __future__ import annotations

from pathlib import Path

from .types import ToolError, ToolResult
from .workspace import resolve_in_workspace as _resolve_in_workspace
from .tools.glob_search import glob_file_search as _glob_file_search_impl
from .tools.grep import grep as _grep_impl
from .tools.list_dir import list_dir as _list_dir_impl
from .tools.patching import apply_patch as _apply_patch_impl
from .tools.patching import undo_patch as _undo_patch_impl
from .tools.read_file import read_file as _read_file_impl
from .tools.repo_map import generate_repo_map as _generate_repo_map_impl
from .tools.run_cmd import run_cmd as _run_cmd_impl
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

    def write_file(self, path: str, text: str) -> ToolResult:
        return _write_file_impl(workspace_root=self.workspace_root, path=path, text=text)

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

    def grep(self, pattern: str, path: str = ".", ignore_case: bool = False, max_hits: int = 200) -> ToolResult:
        return _grep_impl(workspace_root=self.workspace_root, pattern=pattern, path=path, ignore_case=ignore_case, max_hits=max_hits)

    def generate_repo_map(self) -> str:
        return _generate_repo_map_impl(workspace_root=self.workspace_root)

    def run_cmd(self, command: str, cwd: str = ".") -> ToolResult:
        return _run_cmd_impl(
            workspace_root=self.workspace_root,
            max_output_bytes=self.max_output_bytes,
            command=command,
            cwd=cwd,
        )


