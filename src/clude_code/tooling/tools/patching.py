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
    增强的Patch-first editing（参考Claude Code的最佳实践）。
    支持精确匹配、模糊匹配、上下文感知和编辑影响分析。
    返回 payload 包含 before/after hash 与 undo_id。
    """
    p = resolve_in_workspace(workspace_root, path)
    if not p.exists() or not p.is_file():
        return ToolResult(False, error={"code": "E_NOT_FILE", "message": f"not a file: {path}"})

    before_text = p.read_text(encoding="utf-8", errors="replace")
    before_hash = _sha256_text(before_text)

    # 增强的patch验证
    from clude_code.tooling.enhanced_patching import get_enhanced_patch_engine
    patch_engine = get_enhanced_patch_engine()

    # 验证patch合理性
    is_valid, validation_msg = patch_engine.validate_patch(before_text, old, new)
    if not is_valid:
        return ToolResult(False, error={"code": "E_VALIDATION_FAILED", "message": validation_msg})

    # 首先尝试精确匹配
    mode = "exact"
    matched_similarity: float | None = None
    replacements = 0
    updated_text = before_text

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
        # 精确匹配失败，尝试增强的上下文感知匹配
        if not fuzzy:
            return ToolResult(False, error={"code": "E_NOT_FOUND", "message": "old block not found in file"})

        if expected_replacements != 1:
            return ToolResult(False, error={"code": "E_UNSUPPORTED", "message": "fuzzy matching only supports expected_replacements=1"})

        # 使用增强patch引擎进行上下文匹配
        success, error_msg, details = patch_engine.apply_patch_with_context(p, old, new)

        if not success:
            return ToolResult(False, error={"code": "E_FUZZY_FAILED", "message": error_msg})

        mode = "enhanced_fuzzy"
        matched_similarity = details.get('similarity', 0.0)
        replacements = 1

        # 重新读取更新后的内容
        updated_text = p.read_text(encoding="utf-8", errors="replace")

    after_hash = _sha256_text(updated_text)

    # 分析编辑影响
    impact_analysis = patch_engine.analyze_edit_impact(before_text, updated_text)

    # 创建增强的备份
    metadata = {
        "mode": mode,
        "replacements": replacements,
        "matched_similarity": matched_similarity,
        "impact_analysis": impact_analysis,
        "old_content_length": len(before_text),
        "new_content_length": len(updated_text),
        "diff": patch_engine.generate_diff(before_text, updated_text)
    }

    undo_dir = workspace_root / ".clude" / "undo"
    undo_dir.mkdir(parents=True, exist_ok=True)
    undo_id = f"undo_{time.time_ns()}"

    # 使用增强的备份创建
    backup_file = patch_engine.create_backup_with_metadata(p, "apply_patch", metadata)
    bak_path = Path(backup_file)

    # 创建元数据文件
    meta_path = undo_dir / f"{undo_id}.json"
    meta_path.write_text(
        json.dumps(
            {
                "undo_id": undo_id,
                "path": path,
                "created_at_ns": time.time_ns(),
                "before_hash": before_hash,
                "after_hash": after_hash,
                "backup_file": str(bak_path),
                "metadata": metadata,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    # 写入更新后的内容
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
            "impact_analysis": impact_analysis,
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


