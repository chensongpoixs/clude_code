"""
检查 docs/ 目录下是否存在“英文未加中文注释”的行。

目标（Goal/目标）：
- 发现包含英文 (A-Z/a-z) 但缺少中文字符的行，并输出文件:行号:内容，便于逐条修复。

规则（Rules/规则）：
- 仅扫描 docs/**/*.md
- 忽略代码块内的行（``` ... ```）
- 忽略纯链接/图片链接行（含 http/https 或 markdown link 结构）
- 忽略只包含路径/命令的行（例如 `pip install ...`），因为这类通常不适合强行加中文到代码块内

用法（Usage/用法）：
    python tools/check_docs_bilingual.py
"""

from __future__ import annotations

import re
from pathlib import Path


_RE_HAS_LATIN = re.compile(r"[A-Za-z]")
_RE_HAS_CN = re.compile(r"[\u4e00-\u9fff]")


def _is_fence(line: str) -> bool:
    s = line.strip()
    return s.startswith("```")


def _looks_like_link_only(line: str) -> bool:
    s = line.strip()
    if not s:
        return True
    if "http://" in s or "https://" in s:
        return True
    # 纯图片/链接行：![..](..) 或 [..](..)
    if re.fullmatch(r"!?\[[^\]]*\]\([^)]+\)", s):
        return True
    return False


def _looks_like_commandish(line: str) -> bool:
    # 很粗略：包含反引号或 shell 片段，一般不要求强制在行内夹中文
    s = line.strip()
    if s.startswith("`") and s.endswith("`"):
        return True
    if s.startswith("- `") or s.startswith("* `"):
        return True
    return False


def scan_docs(root: Path) -> list[str]:
    docs_dir = root / "docs"
    if not docs_dir.exists():
        return ["E_NO_DOCS: docs/ directory not found (未找到 docs/ 目录)"]

    findings: list[str] = []
    for md in sorted(docs_dir.rglob("*.md")):
        in_fence = False
        try:
            text = md.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            findings.append(f"- {md.as_posix()}:0 -> E_READ ({e})")
            continue

        for idx, raw in enumerate(text.splitlines(), start=1):
            line = raw.rstrip("\n")
            if _is_fence(line):
                in_fence = not in_fence
                continue
            if in_fence:
                continue

            if not _RE_HAS_LATIN.search(line):
                continue
            if _RE_HAS_CN.search(line):
                continue

            if _looks_like_link_only(line):
                continue
            if _looks_like_commandish(line):
                continue

            # 允许少量缩写，但仍建议补注释；这里先全部报出来
            rel = md.relative_to(root).as_posix()
            snippet = line.strip()
            if len(snippet) > 200:
                snippet = snippet[:200] + "…"
            findings.append(f"- {rel}:{idx} -> {snippet}")

    return findings


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    findings = scan_docs(root)
    if findings and not (len(findings) == 1 and findings[0].startswith("E_NO_DOCS")):
        print(f"FOUND {len(findings)} lines with English but no Chinese annotations:")
        for f in findings[:500]:
            print(f)
        if len(findings) > 500:
            print(f"... truncated, total={len(findings)}")
        return 2
    print("OK: docs bilingual annotations look complete (no suspicious lines found).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


