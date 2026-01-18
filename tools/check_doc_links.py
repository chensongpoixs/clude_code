from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Tuple


RE_MD_LINK = re.compile(r"(!?\[[^\]]*\])\(([^)]+)\)")


@dataclass(frozen=True)
class LinkHit:
    md_file: Path
    line_no: int
    raw_target: str
    is_image: bool


@dataclass(frozen=True)
class BrokenLink:
    md_file: Path
    line_no: int
    raw_target: str
    resolved_path: Path
    reason: str


def _is_external(target: str) -> bool:
    t = target.strip()
    return (
        t.startswith("http://")
        or t.startswith("https://")
        or t.startswith("mailto:")
        or t.startswith("tel:")
    )


def _strip_wrappers(target: str) -> str:
    # Remove optional <...> wrapper (common in Markdown).
    t = target.strip()
    if t.startswith("<") and t.endswith(">"):
        t = t[1:-1].strip()
    # Remove surrounding quotes if present.
    if (t.startswith('"') and t.endswith('"')) or (t.startswith("'") and t.endswith("'")):
        t = t[1:-1].strip()
    return t


def _split_target(target: str) -> Tuple[str, Optional[str]]:
    """
    Returns (path_part, anchor_part_without_hash).
    """
    t = _strip_wrappers(target)
    if "#" in t:
        path_part, anchor = t.split("#", 1)
        return path_part, anchor or None
    return t, None


def iter_md_files(repo_root: Path) -> Iterable[Path]:
    for p in repo_root.rglob("*.md"):
        # Skip virtual envs / caches if they exist.
        parts = {x.lower() for x in p.parts}
        if "node_modules" in parts or ".venv" in parts or "__pycache__" in parts:
            continue
        yield p


def iter_links(md_file: Path) -> Iterable[LinkHit]:
    try:
        text = md_file.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = md_file.read_text(encoding="utf-8", errors="replace")
    for i, line in enumerate(text.splitlines(), start=1):
        for m in RE_MD_LINK.finditer(line):
            label = m.group(1)
            raw_target = m.group(2).strip()
            is_image = label.startswith("![")
            yield LinkHit(md_file=md_file, line_no=i, raw_target=raw_target, is_image=is_image)


def _resolve(repo_root: Path, md_file: Path, path_part: str) -> Optional[Path]:
    pp = path_part.strip()
    if not pp:
        return None
    if _is_external(pp):
        return None
    # Absolute repo-root style: /docs/xx.md
    if pp.startswith("/"):
        return (repo_root / pp.lstrip("/")).resolve()
    return (md_file.parent / pp).resolve()


def find_broken_links(repo_root: Path) -> List[BrokenLink]:
    broken: List[BrokenLink] = []
    for md in iter_md_files(repo_root):
        for hit in iter_links(md):
            path_part, _anchor = _split_target(hit.raw_target)
            if _is_external(path_part):
                continue
            resolved = _resolve(repo_root, md, path_part)
            if resolved is None:
                continue
            # For directory links, accept if directory exists.
            if resolved.exists():
                continue
            broken.append(
                BrokenLink(
                    md_file=md,
                    line_no=hit.line_no,
                    raw_target=hit.raw_target,
                    resolved_path=resolved,
                    reason="path_not_found",
                )
            )
    return broken


def main() -> int:
    repo_root = Path(os.getcwd()).resolve()
    broken = find_broken_links(repo_root)
    if not broken:
        print("OK: no broken local markdown links found.")
        return 0

    print(f"FOUND {len(broken)} broken local markdown links:")
    for b in broken:
        rel_md = b.md_file.relative_to(repo_root)
        rel_target = b.resolved_path
        try:
            rel_target = b.resolved_path.relative_to(repo_root)
        except Exception:
            pass
        print(f"- {rel_md}:{b.line_no} -> ({b.raw_target})  [resolved={rel_target}]  reason={b.reason}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())


