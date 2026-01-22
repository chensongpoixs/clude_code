from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MergeResult:
    ok: bool
    copied_files: int = 0
    error: str = ""


def _is_within(root: Path, p: Path) -> bool:
    try:
        p.resolve().relative_to(root.resolve())
        return True
    except Exception:
        return False


def merge_modified_files(
    *,
    sandbox_root: Path,
    workspace_root: Path,
    modified_abs_paths_in_workspace: list[Path],
) -> MergeResult:
    """
    MVP 合并策略：把“在主 workspace 下的绝对路径列表”映射到沙箱中同路径文件，
    将其复制回主 workspace（覆盖）。
    """
    copied = 0
    for abs_path in modified_abs_paths_in_workspace:
        try:
            if not _is_within(workspace_root, abs_path):
                return MergeResult(ok=False, copied_files=copied, error=f"path outside workspace: {abs_path}")

            rel = abs_path.resolve().relative_to(workspace_root.resolve())
            src = (sandbox_root / rel).resolve()
            dst = abs_path.resolve()

            if not _is_within(sandbox_root, src):
                return MergeResult(ok=False, copied_files=copied, error=f"path outside sandbox: {src}")

            if not src.exists():
                return MergeResult(ok=False, copied_files=copied, error=f"sandbox file missing: {src}")

            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            copied += 1
        except Exception as e:
            return MergeResult(ok=False, copied_files=copied, error=f"{type(e).__name__}: {e}")

    return MergeResult(ok=True, copied_files=copied)


