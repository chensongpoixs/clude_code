from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


SandboxType = Literal["worktree", "copy"]


@dataclass
class SandboxContext:
    sandbox_id: str
    kind: SandboxType
    sandbox_root: Path
    # worktree 专用
    worktree_branch: str | None = None


def _is_git_repo(path: Path) -> bool:
    return (path / ".git").exists()


def _which_git() -> str | None:
    from shutil import which

    return which("git")


def _run_git(args: list[str], *, cwd: Path, timeout_s: int = 60) -> tuple[int, str]:
    try:
        p = subprocess.run(
            args,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout_s,
            check=False,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return int(p.returncode), str(p.stdout or "")
    except Exception as e:
        return 1, f"git_run_failed: {type(e).__name__}: {e}"


def _copy_workspace(src: Path, dst: Path) -> None:
    ignore = shutil.ignore_patterns(
        ".git",
        ".clude",
        "node_modules",
        ".venv",
        "venv",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
    )
    shutil.copytree(src, dst, dirs_exist_ok=False, ignore=ignore)


class SandboxRunner:
    """
    Phase 3：SandboxRunner（git worktree 优先，fallback temp copy）
    """

    def __init__(self, workspace_root: str | Path) -> None:
        self.workspace_root = Path(workspace_root).resolve()

    def create(self, *, prefer: SandboxType = "worktree") -> SandboxContext:
        sandbox_id = f"sbx_{int(time.time())}"

        if prefer == "worktree":
            ctx = self._try_create_worktree(sandbox_id)
            if ctx is not None:
                return ctx

        return self._create_copy(sandbox_id)

    def _try_create_worktree(self, sandbox_id: str) -> SandboxContext | None:
        if not _is_git_repo(self.workspace_root):
            return None
        if not _which_git():
            return None

        sandbox_dir = Path(tempfile.gettempdir()) / f"clude_worktree_{sandbox_id}"
        if sandbox_dir.exists():
            shutil.rmtree(sandbox_dir, ignore_errors=True)

        branch = f"clude_sandbox_{sandbox_id}"
        # worktree add
        code, out = _run_git(["git", "worktree", "add", str(sandbox_dir), "-b", branch], cwd=self.workspace_root, timeout_s=120)
        if code != 0:
            return None

        return SandboxContext(sandbox_id=sandbox_id, kind="worktree", sandbox_root=sandbox_dir, worktree_branch=branch)

    def _create_copy(self, sandbox_id: str) -> SandboxContext:
        sandbox_dir = Path(tempfile.gettempdir()) / f"clude_sandbox_{sandbox_id}"
        if sandbox_dir.exists():
            shutil.rmtree(sandbox_dir, ignore_errors=True)
        _copy_workspace(self.workspace_root, sandbox_dir)
        return SandboxContext(sandbox_id=sandbox_id, kind="copy", sandbox_root=sandbox_dir)

    def discard(self, ctx: SandboxContext) -> None:
        """
        丢弃沙箱（回滚）：删除目录；worktree 还需 remove。
        """
        try:
            if ctx.kind == "worktree" and _which_git() and ctx.sandbox_root.exists():
                _run_git(["git", "worktree", "remove", "--force", str(ctx.sandbox_root)], cwd=self.workspace_root, timeout_s=120)
                if ctx.worktree_branch:
                    _run_git(["git", "branch", "-D", ctx.worktree_branch], cwd=self.workspace_root, timeout_s=60)
        finally:
            shutil.rmtree(ctx.sandbox_root, ignore_errors=True)


