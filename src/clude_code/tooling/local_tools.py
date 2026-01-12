from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


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

    def grep(self, pattern: str, path: str = ".", ignore_case: bool = False, max_hits: int = 200) -> ToolResult:
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
                        return ToolResult(True, payload={"pattern": pattern, "hits": hits, "truncated": True})
        return ToolResult(True, payload={"pattern": pattern, "hits": hits, "truncated": False})

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


