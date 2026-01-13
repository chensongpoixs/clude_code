from __future__ import annotations

import hashlib
import json
import time
from difflib import SequenceMatcher
from pathlib import Path

from ..types import ToolResult
from ..workspace import resolve_in_workspace


def _sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", errors="ignore")).hexdigest()


def apply_patch(
    *,
    workspace_root: Path,
    path: str,
    old: str,
    new: str,
    expected_replacements: int = 1,
    fuzzy: bool = False,
    min_similarity: float = 0.92,
) -> ToolResult:
    """
    Patch-first editing（支持 fuzzy 单点替换）。
    返回 payload 包含 before/after hash 与 undo_id。
    """
    p = resolve_in_workspace(workspace_root, path)
    if not p.exists() or not p.is_file():
        return ToolResult(False, error={"code": "E_NOT_FILE", "message": f"not a file: {path}"})

    before_text = p.read_text(encoding="utf-8", errors="replace")
    before_hash = _sha256_text(before_text)

    replacements = 0
    updated_text = before_text
    mode = "exact"
    matched_similarity: float | None = None

    if old in before_text:
        count = before_text.count(old)
        if expected_replacements > 0 and count != expected_replacements:
            return ToolResult(
                False,
                error={"code": "E_NOT_UNIQUE", "message": f"old block occurrences={count}, expected={expected_replacements}"},
            )
        if expected_replacements == 0:
            replacements = count
            updated_text = before_text.replace(old, new)
        else:
            replacements = expected_replacements
            updated_text = before_text.replace(old, new, expected_replacements)
    else:
        if not fuzzy:
            return ToolResult(False, error={"code": "E_NOT_FOUND", "message": "old block not found in file"})
        if expected_replacements != 1:
            return ToolResult(False, error={"code": "E_UNSUPPORTED", "message": "fuzzy matching only supports expected_replacements=1"})

        old_lines = old.splitlines()
        file_lines = before_text.splitlines()
        n = max(len(old_lines), 1)

        anchor = ""
        for ln in sorted((l.strip() for l in old_lines), key=len, reverse=True):
            if ln:
                anchor = ln[:120]
                break

        candidate_starts: list[int] = []
        if anchor:
            for i, ln in enumerate(file_lines):
                if anchor in ln:
                    candidate_starts.append(max(i - n // 2, 0))
        else:
            candidate_starts = list(range(0, max(len(file_lines) - n + 1, 1)))

        best = None
        best_ratio = 0.0
        candidate_starts = candidate_starts[:200]
        for start in candidate_starts:
            for span in (n, max(n - 1, 1), n + 1):
                if start + span > len(file_lines):
                    continue
                cand = "\n".join(file_lines[start : start + span])
                r = SequenceMatcher(None, old, cand).ratio()
                if r > best_ratio:
                    best_ratio = r
                    best = cand

        if best is None or best_ratio < float(min_similarity):
            return ToolResult(
                False,
                error={
                    "code": "E_FUZZY_NO_MATCH",
                    "message": f"no fuzzy match above min_similarity={min_similarity}, best={best_ratio:.3f}",
                },
            )

        mode = "fuzzy"
        matched_similarity = best_ratio
        updated_text = before_text.replace(best, new, 1)
        replacements = 1

    after_hash = _sha256_text(updated_text)

    undo_dir = workspace_root / ".clude" / "undo"
    undo_dir.mkdir(parents=True, exist_ok=True)
    undo_id = f"undo_{time.time_ns()}"
    bak_path = undo_dir / f"{undo_id}.bak"
    meta_path = undo_dir / f"{undo_id}.json"

    bak_path.write_text(before_text, encoding="utf-8")
    meta_path.write_text(
        json.dumps(
            {
                "undo_id": undo_id,
                "path": path,
                "created_at_ns": time.time_ns(),
                "before_hash": before_hash,
                "after_hash": after_hash,
                "backup_file": str(bak_path),
                "mode": mode,
                "replacements": replacements,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    p.write_text(updated_text, encoding="utf-8")
    return ToolResult(
        True,
        payload={
            "path": path,
            "mode": mode,
            "replacements": replacements,
            "expected_replacements": expected_replacements,
            "fuzzy": fuzzy,
            "min_similarity": min_similarity,
            "matched_similarity": matched_similarity,
            "before_hash": before_hash,
            "after_hash": after_hash,
            "undo_id": undo_id,
        },
    )


def undo_patch(*, workspace_root: Path, undo_id: str, force: bool = False) -> ToolResult:
    """
    从 `.clude/undo/{undo_id}.bak` 恢复文件。
    默认校验当前文件 hash == 记录的 after_hash，避免覆盖无关改动；force=True 可强制恢复。
    """
    undo_dir = workspace_root / ".clude" / "undo"
    meta_path = undo_dir / f"{undo_id}.json"
    if not meta_path.exists():
        return ToolResult(False, error={"code": "E_UNDO_NOT_FOUND", "message": f"undo_id not found: {undo_id}"})

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    path = str(meta["path"])
    p = resolve_in_workspace(workspace_root, path)
    if not p.exists() or not p.is_file():
        return ToolResult(False, error={"code": "E_NOT_FILE", "message": f"not a file: {path}"})

    current_text = p.read_text(encoding="utf-8", errors="replace")
    current_hash = _sha256_text(current_text)
    expected_after = str(meta.get("after_hash", ""))
    if (not force) and expected_after and current_hash != expected_after:
        return ToolResult(
            False,
            error={
                "code": "E_UNDO_CONFLICT",
                "message": "current file hash does not match undo record (use force=true to override)",
                "details": {"current_hash": current_hash, "expected_after_hash": expected_after},
            },
        )

    bak_path = Path(str(meta["backup_file"]))
    if not bak_path.exists():
        return ToolResult(False, error={"code": "E_UNDO_BAK_MISSING", "message": "backup file missing"})

    before_text = bak_path.read_text(encoding="utf-8", errors="replace")
    before_hash = _sha256_text(before_text)

    p.write_text(before_text, encoding="utf-8")
    restored_hash = _sha256_text(before_text)
    return ToolResult(
        True,
        payload={
            "undo_id": undo_id,
            "path": path,
            "force": force,
            "restored_hash": restored_hash,
            "recorded_before_hash": str(meta.get("before_hash", "")),
            "recorded_after_hash": expected_after,
            "current_hash_before_restore": current_hash,
            "before_hash": before_hash,
        },
    )


