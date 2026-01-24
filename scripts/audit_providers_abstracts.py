#!/usr/bin/env python3
"""
审计 providers 实现是否满足 LLMProvider 抽象方法契约。

检查项：
1) Provider 类是否实现 chat/list_models（必需）
2) chat_async/chat_stream 视为“可选能力”（基类提供默认降级实现），因此不再作为缺失项报错
2) __init__ 是否接受 (self, config: ProviderConfig) 形参（至少能接收一个 config）

说明：
- 使用 AST 静态分析，避免导入时触发第三方依赖/网络。
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path


PROVIDERS_DIR = Path("src/clude_code/llm/providers")


@dataclass
class ProviderIssue:
    file: str
    cls: str
    kind: str
    detail: str


def _is_llmprovider_subclass(node: ast.ClassDef) -> bool:
    for b in node.bases:
        # class X(LLMProvider)
        if isinstance(b, ast.Name) and b.id == "LLMProvider":
            return True
        # class X(pkg.LLMProvider)
        if isinstance(b, ast.Attribute) and b.attr == "LLMProvider":
            return True
    return False


def _collect_methods(node: ast.ClassDef) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    out: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
    for item in node.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out[item.name] = item
    return out


def _check_init_signature(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> str | None:
    # 允许 __init__(self, config) / __init__(self, config, ...) / __init__(self, config: ProviderConfig, ...)
    args = fn.args
    pos = list(args.posonlyargs) + list(args.args)
    if not pos:
        return "__init__ 缺少 self"
    # pos[0] should be self
    if len(pos) < 2:
        return "__init__ 未接受 config 参数"
    # 第二个参数名应是 config（弱约束：只要存在即可）
    return None


def audit() -> list[ProviderIssue]:
    issues: list[ProviderIssue] = []
    for py in sorted(PROVIDERS_DIR.glob("*.py")):
        if py.name.startswith("__"):
            continue
        src = py.read_text(encoding="utf-8")
        try:
            tree = ast.parse(src)
        except SyntaxError as e:
            issues.append(ProviderIssue(py.name, "<parse>", "syntax_error", str(e)))
            continue

        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            if not _is_llmprovider_subclass(node):
                continue

            methods = _collect_methods(node)
            cls_name = node.name

            # required methods per LLMProvider（必需）
            required = ["chat", "list_models"]
            for m in required:
                if m not in methods:
                    issues.append(ProviderIssue(py.name, cls_name, "missing_method", m))

            init = methods.get("__init__")
            if init:
                err = _check_init_signature(init)
                if err:
                    issues.append(ProviderIssue(py.name, cls_name, "bad_init", err))
            else:
                # 没有 __init__ 也 OK（继承基类 __init__）
                pass

    return issues


def main() -> None:
    issues = audit()
    print(f"providers scanned: {len(list(PROVIDERS_DIR.glob('*.py')))}")
    if not issues:
        print("OK: no issues found")
        return
    print(f"issues: {len(issues)}")
    for it in issues:
        print(f"- {it.file}:{it.cls} [{it.kind}] {it.detail}")


if __name__ == "__main__":
    main()


