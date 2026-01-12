from __future__ import annotations

import hashlib
import json
import re
import subprocess
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from difflib import SequenceMatcher


class ToolError(RuntimeError):
    pass


def _resolve_in_workspace(workspace_root: Path, user_path: str) -> Path:
    root = workspace_root.resolve()
    p = (root / user_path).resolve()
    try:
        p.relative_to(root)
    except ValueError as e:
        raise ToolError(f"path is outside workspace: {user_path}") from e
    return p


@dataclass(frozen=True)
class ToolResult:
    ok: bool
    payload: dict[str, Any] | None = None
    error: dict[str, Any] | None = None


class LocalTools:
    def __init__(self, workspace_root: str, *, max_file_read_bytes: int, max_output_bytes: int) -> None:
        self.workspace_root = Path(workspace_root)
        self.max_file_read_bytes = max_file_read_bytes
        self.max_output_bytes = max_output_bytes

    def list_dir(self, path: str = ".") -> ToolResult:
        p = _resolve_in_workspace(self.workspace_root, path)
        if not p.exists() or not p.is_dir():
            return ToolResult(False, error={"code": "E_NOT_DIR", "message": f"not a directory: {path}"})
        items = []
        for child in sorted(p.iterdir(), key=lambda x: x.name.lower()):
            items.append(
                {
                    "name": child.name,
                    "is_dir": child.is_dir(),
                    "size_bytes": child.stat().st_size if child.is_file() else None,
                }
            )
        return ToolResult(True, payload={"path": path, "items": items})

    def read_file(self, path: str, offset: int | None = None, limit: int | None = None) -> ToolResult:
        p = _resolve_in_workspace(self.workspace_root, path)
        if not p.exists() or not p.is_file():
            return ToolResult(False, error={"code": "E_NOT_FILE", "message": f"not a file: {path}"})
        data = p.read_bytes()
        if len(data) > self.max_file_read_bytes:
            data = data[: self.max_file_read_bytes]
        text = data.decode("utf-8", errors="replace")
        lines = text.splitlines()
        if offset is None and limit is None:
            return ToolResult(True, payload={"path": path, "text": text})
        start = max((offset or 1) - 1, 0)
        end = start + (limit or 200)
        sliced = "\n".join(lines[start:end])
        return ToolResult(True, payload={"path": path, "offset": offset, "limit": limit, "text": sliced})

    def write_file(self, path: str, text: str) -> ToolResult:
        p = _resolve_in_workspace(self.workspace_root, path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return ToolResult(True, payload={"path": path, "bytes_written": len(text.encode("utf-8"))})

    def apply_patch(
        self,
        path: str,
        old: str,
        new: str,
        expected_replacements: int = 1,
        fuzzy: bool = False,
        min_similarity: float = 0.92,
    ) -> ToolResult:
        """
        Patch-first editing:
        - Replace occurrences of `old` with `new` in a file.
        - If expected_replacements > 0: require exact count match, then replace that many.
        - If expected_replacements == 0: replace all occurrences.
        - Optional fuzzy matching (single replacement only) when `old` is not found.

        Guidance for the model: include enough surrounding context in `old` so it matches uniquely.
        """
        p = _resolve_in_workspace(self.workspace_root, path)
        if not p.exists() or not p.is_file():
            return ToolResult(False, error={"code": "E_NOT_FILE", "message": f"not a file: {path}"})
        before_text = p.read_text(encoding="utf-8", errors="replace")
        before_hash = hashlib.sha256(before_text.encode("utf-8", errors="ignore")).hexdigest()

        replacements = 0
        updated_text = before_text
        mode = "exact"
        matched_similarity: float | None = None

        if old in before_text:
            count = before_text.count(old)
            if expected_replacements > 0 and count != expected_replacements:
                return ToolResult(
                    False,
                    error={
                        "code": "E_NOT_UNIQUE",
                        "message": f"old block occurrences={count}, expected={expected_replacements}",
                    },
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
                return ToolResult(
                    False,
                    error={"code": "E_UNSUPPORTED", "message": "fuzzy matching only supports expected_replacements=1"},
                )
            # Fuzzy match: anchor-based window search on lines to find the closest block.
            old_lines = old.splitlines()
            file_lines = before_text.splitlines()
            n = max(len(old_lines), 1)

            # choose an anchor line to narrow candidates
            anchor = ""
            for ln in sorted((l.strip() for l in old_lines), key=len, reverse=True):
                if ln:
                    anchor = ln[:120]
                    break

            candidate_starts: list[int] = []
            if anchor:
                for i, ln in enumerate(file_lines):
                    if anchor in ln:
                        # assume anchor roughly in the middle of the block
                        candidate_starts.append(max(i - n // 2, 0))
            else:
                candidate_starts = list(range(0, max(len(file_lines) - n + 1, 1)))

            best = None
            best_ratio = 0.0
            best_len = n
            # limit candidates for performance
            candidate_starts = candidate_starts[:200]
            for start in candidate_starts:
                for span in (n, max(n - 1, 1), n + 1):
                    if start + span > len(file_lines):
                        continue
                    cand = "\n".join(file_lines[start : start + span])
                    r = SequenceMatcher(None, old, cand).ratio()
                    if r > best_ratio:
                        best_ratio = r
                        best = (start, cand)
                        best_len = span
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
            start, cand = best
            # replace the exact candidate block string once
            updated_text = before_text.replace(cand, new, 1)
            replacements = 1

        # Write undo backup + metadata (MVP: full file backup)
        after_hash = hashlib.sha256(updated_text.encode("utf-8", errors="ignore")).hexdigest()
        undo_dir = self.workspace_root / ".clude" / "undo"
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

    def undo_patch(self, undo_id: str, force: bool = False) -> ToolResult:
        """
        Restore a file from `.clude/undo/{undo_id}.bak`.

        - By default, verifies current file hash == recorded after_hash, to prevent overwriting unrelated edits.
        - If force=True, restore anyway.
        """
        undo_dir = self.workspace_root / ".clude" / "undo"
        meta_path = undo_dir / f"{undo_id}.json"
        if not meta_path.exists():
            return ToolResult(False, error={"code": "E_UNDO_NOT_FOUND", "message": f"undo_id not found: {undo_id}"})
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        path = str(meta["path"])
        p = _resolve_in_workspace(self.workspace_root, path)
        if not p.exists() or not p.is_file():
            return ToolResult(False, error={"code": "E_NOT_FILE", "message": f"not a file: {path}"})

        current_text = p.read_text(encoding="utf-8", errors="replace")
        current_hash = hashlib.sha256(current_text.encode("utf-8", errors="ignore")).hexdigest()
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
        before_hash = hashlib.sha256(before_text.encode("utf-8", errors="ignore")).hexdigest()

        p.write_text(before_text, encoding="utf-8")
        restored_hash = hashlib.sha256(before_text.encode("utf-8", errors="ignore")).hexdigest()
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

    def grep(self, pattern: str, path: str = ".", ignore_case: bool = False, max_hits: int = 200) -> ToolResult:
        """
        Prefer ripgrep (rg) for deterministic performance and structured output.
        Fallback to Python rglob+regex if rg is not available.
        """
        if shutil.which("rg"):
            tr = self._rg_grep(pattern=pattern, path=path, ignore_case=ignore_case, max_hits=max_hits)
            if tr.ok:
                return tr
        return self._python_grep(pattern=pattern, path=path, ignore_case=ignore_case, max_hits=max_hits)

    def _rg_grep(self, *, pattern: str, path: str, ignore_case: bool, max_hits: int) -> ToolResult:
        root = _resolve_in_workspace(self.workspace_root, path)
        if not root.exists():
            return ToolResult(False, error={"code": "E_NOT_FOUND", "message": f"path not found: {path}"})

        args = ["rg", "--json"]
        if ignore_case:
            args.append("-i")
        args.append(pattern)
        # run rg scoped to the given path, with cwd at workspace root to keep paths relative
        args.append(path)

        try:
            cp = subprocess.run(
                args,
                cwd=str(self.workspace_root.resolve()),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                shell=False,
            )
        except Exception as e:
            return ToolResult(False, error={"code": "E_RG_EXEC", "message": str(e)})

        # rg returns 1 when no matches; treat as ok with empty hits
        if cp.returncode not in (0, 1):
            return ToolResult(
                False,
                error={"code": "E_RG", "message": "rg failed", "details": {"stderr": (cp.stderr or "")[:2000]}},
            )

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
            ln = (((data.get("line_number"))) if "line_number" in data else None)
            lines = (data.get("lines") or {}).get("text") if isinstance(data.get("lines"), dict) else ""
            hits.append({"path": p, "line": ln, "preview": str(lines)[:300]})

        truncated = False
        if len(hits) > max_hits:
            truncated = True
            hits = hits[:max_hits]

        return ToolResult(True, payload={"pattern": pattern, "engine": "rg", "hits": hits, "truncated": truncated})

    def _python_grep(self, *, pattern: str, path: str, ignore_case: bool, max_hits: int) -> ToolResult:
        root = _resolve_in_workspace(self.workspace_root, path)
        if not root.exists():
            return ToolResult(False, error={"code": "E_NOT_FOUND", "message": f"path not found: {path}"})
        flags = re.IGNORECASE if ignore_case else 0
        try:
            rx = re.compile(pattern, flags)
        except re.error as e:
            return ToolResult(False, error={"code": "E_INVALID_REGEX", "message": str(e)})

        hits = []
        for fp in root.rglob("*"):
            if fp.is_dir():
                continue
            # skip very large/binary-ish files
            try:
                if fp.stat().st_size > 2_000_000:
                    continue
                content = fp.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for i, line in enumerate(content.splitlines(), start=1):
                if rx.search(line):
                    rel = str(fp.resolve().relative_to(self.workspace_root.resolve()))
                    hits.append({"path": rel, "line": i, "preview": line[:300]})
                    if len(hits) >= max_hits:
                        return ToolResult(True, payload={"pattern": pattern, "engine": "python", "hits": hits, "truncated": True})
        return ToolResult(True, payload={"pattern": pattern, "engine": "python", "hits": hits, "truncated": False})

    def generate_repo_map(self) -> str:
        """
        Generate a concise map of the repository's symbols using ctags.
        Returns a formatted string describing classes and functions in the codebase.
        """
        ctags_exe = shutil.which("ctags")
        if not ctags_exe:
            return "Repo Map: ctags not found. Global symbol context unavailable."

        # Scan key source files, exclude known large/irrelevant dirs
        # Using a simplified approach: run ctags on the whole workspace
        args = [
            ctags_exe,
            "--languages=Python,JavaScript,TypeScript,Go,Java,Rust,C,C++,C#",
            "--output-format=json",
            "--fields=+n",
            "-R",
            ".",
        ]
        
        try:
            # Exclude node_modules, .venv, etc. to keep it fast
            cp = subprocess.run(
                args,
                cwd=str(self.workspace_root.resolve()),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except Exception:
            return "Repo Map: Failed to execute ctags."

        if cp.returncode != 0:
            return f"Repo Map: ctags failed with code {cp.returncode}."

        symbols_by_file: dict[str, list[str]] = {}
        for line in cp.stdout.splitlines():
            try:
                obj = json.loads(line)
                if not isinstance(obj, dict): continue
                
                path = obj.get("path")
                name = obj.get("name")
                kind = obj.get("kind")
                line_no = obj.get("line")
                
                if not all([path, name, kind]): continue
                
                # Filter noise: only keep high-level symbols
                if kind not in ("class", "function", "method", "member", "interface", "struct"):
                    continue
                
                if path not in symbols_by_file:
                    symbols_by_file[path] = []
                
                symbols_by_file[path].append(f"{kind[0].upper()}| {name} (L{line_no})")
            except json.JSONDecodeError:
                continue

        lines = ["# Repository Map (Symbols)"]
        # Limit to 100 most relevant files to keep token usage sane
        sorted_files = sorted(symbols_by_file.keys())[:100]
        for f in sorted_files:
            lines.append(f"## {f}")
            # Limit symbols per file
            syms = symbols_by_file[f][:15]
            for s in syms:
                lines.append(f"  - {s}")
            if len(symbols_by_file[f]) > 15:
                lines.append("  - ...")
        
        return "\n".join(lines)

    def run_cmd(self, command: str, cwd: str = ".") -> ToolResult:
        wd = _resolve_in_workspace(self.workspace_root, cwd)
        try:
            cp = subprocess.run(
                command,
                cwd=str(wd),
                shell=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except Exception as e:
            return ToolResult(False, error={"code": "E_EXEC", "message": str(e)})
        out = (cp.stdout or "") + (cp.stderr or "")
        if len(out.encode("utf-8", errors="ignore")) > self.max_output_bytes:
            out = out[-self.max_output_bytes :]
        return ToolResult(True, payload={"command": command, "cwd": cwd, "exit_code": cp.returncode, "output": out})


