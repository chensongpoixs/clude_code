from __future__ import annotations

import json
import platform
import shutil
import subprocess
from pathlib import Path


def generate_repo_map(*, workspace_root: Path) -> str:
    """
    使用 ctags 生成仓库符号概览（Repo Map）。
    返回字符串（供 system prompt 或日志使用），不是 ToolResult。
    """
    ctags_exe = shutil.which("ctags")
    if not ctags_exe:
        return "Repo Map: ctags not found. Global symbol context unavailable."

    args = [
        ctags_exe,
        "--languages=Python,JavaScript,TypeScript,Go,Java,Rust,C,C++,C#",
        "--output-format=json",
        "--fields=+n",
        "-R",
        ".",
    ]

    abs_root = str(workspace_root.resolve())
    try:
        cp = subprocess.run(
            args,
            cwd=abs_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=(platform.system() == "Windows"),
        )
    except Exception:
        return "Repo Map: Failed to execute ctags."

    if cp.returncode != 0:
        return f"Repo Map: ctags failed with code {cp.returncode}."

    symbols_by_file: dict[str, list[str]] = {}
    for line in (cp.stdout or "").splitlines():
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        path = obj.get("path")
        name = obj.get("name")
        kind = obj.get("kind")
        line_no = obj.get("line")
        if not all([path, name, kind]):
            continue
        if kind not in ("class", "function", "method", "member", "interface", "struct"):
            continue
        symbols_by_file.setdefault(path, []).append(f"{kind[0].upper()}| {name} (L{line_no})")

    lines = ["# Repository Map (Symbols)"]
    for f in sorted(symbols_by_file.keys())[:100]:
        lines.append(f"## {f}")
        syms = symbols_by_file[f][:15]
        for s in syms:
            lines.append(f"  - {s}")
        if len(symbols_by_file[f]) > 15:
            lines.append("  - ...")
    return "\n".join(lines)


