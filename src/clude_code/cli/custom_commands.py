from __future__ import annotations

"""
从 `.clude/commands/` 加载自定义 Markdown 命令（对标 Claude Code 的 `.claude/commands`）。

设计原则：
- **最小依赖**：不引入 YAML 依赖，frontmatter 用简易 key:value 解析
- **安全默认**：命令只做“prompt 模板展开”，真正执行仍走 AgentLoop（受 policy/confirm/audit 控制）
- **可扩展**：后续可加入参数 schema、completion、权限声明等
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CustomCommand:
    name: str
    description: str
    template: str
    path: str
    meta: dict[str, Any]


@dataclass(frozen=True)
class ExpandedCommand:
    prompt: str
    command: CustomCommand
    policy_overrides: dict[str, Any]
    errors: list[str]


def _commands_dir(workspace_root: str) -> Path:
    return Path(workspace_root) / ".clude" / "commands"


def _parse_frontmatter(lines: list[str]) -> tuple[dict[str, str], int]:
    """
    解析非常简化的 frontmatter：
    ---
    name: review
    description: xxx
    ---
    返回 (meta, body_start_index)
    """
    if not lines or lines[0].strip() != "---":
        return {}, 0
    meta: dict[str, str] = {}
    i = 1
    while i < len(lines):
        s = lines[i].rstrip("\n")
        if s.strip() == "---":
            return meta, i + 1
        if ":" in s:
            k, v = s.split(":", 1)
            meta[k.strip()] = v.strip()
        i += 1
    return {}, 0


def _split_list(s: str) -> list[str]:
    raw = (s or "").replace(",", " ").strip()
    return [x for x in raw.split() if x]


def _parse_bool(s: str) -> bool | None:
    v = (s or "").strip().lower()
    if v in {"true", "1", "yes", "on"}:
        return True
    if v in {"false", "0", "no", "off"}:
        return False
    return None


def load_custom_commands(workspace_root: str) -> list[CustomCommand]:
    d = _commands_dir(workspace_root)
    if not d.exists():
        return []
    out: list[CustomCommand] = []
    for p in sorted(d.glob("*.md")):
        try:
            raw = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        lines = raw.splitlines()
        meta, start = _parse_frontmatter(lines)
        body = "\n".join(lines[start:]).strip()
        if not body:
            continue

        name = (meta.get("name") or p.stem).strip()
        if name.startswith("/"):
            name = name[1:]
        if not name:
            continue
        desc = (meta.get("description") or "").strip()
        if not desc:
            # 取第一行作为描述（如果是标题行则跳过）
            first = body.splitlines()[0].strip() if body.splitlines() else ""
            desc = first[:80]

        args = _split_list(meta.get("args", ""))
        required = _split_list(meta.get("required", "")) or _split_list(meta.get("required_args", ""))
        usage = (meta.get("usage") or "").strip()
        allowed_tools = _split_list(meta.get("allowed_tools", "")) or _split_list(meta.get("allowedTools", ""))
        disallowed_tools = _split_list(meta.get("disallowed_tools", "")) or _split_list(meta.get("disallowedTools", ""))
        allow_network = _parse_bool(meta.get("allow_network", ""))

        meta2: dict[str, Any] = {
            "args": args,
            "required": required,
            "usage": usage,
            "allowed_tools": allowed_tools,
            "disallowed_tools": disallowed_tools,
        }
        if allow_network is not None:
            meta2["allow_network"] = allow_network

        out.append(CustomCommand(name=name, description=desc, template=body, path=str(p), meta=meta2))
    return out


def expand_custom_command(
    *,
    commands: list[CustomCommand],
    user_text: str,
) -> ExpandedCommand | None:
    """
    将 `/name ...` 展开为 prompt 文本。
    支持占位符：
    - {{args}}：全部参数字符串
    - {{arg1}}, {{arg2}}...：按空格分割的位置参数
    """
    t = (user_text or "").strip()
    if not t.startswith("/"):
        return None
    parts = t.split()
    cmd = parts[0].lstrip("/").strip().lower()
    raw_args = parts[1:]

    # 解析参数：支持 key=value + 位置参数
    kv: dict[str, str] = {}
    pos: list[str] = []
    for tok in raw_args:
        if "=" in tok and not tok.startswith("=") and not tok.endswith("="):
            k, v = tok.split("=", 1)
            k = k.strip()
            v = v.strip()
            if k:
                kv[k] = v
                continue
        pos.append(tok)
    args_str = " ".join(raw_args).strip()

    chosen = None
    for c in commands:
        if c.name.strip().lower() == cmd:
            chosen = c
            break
    if chosen is None:
        return None

    # 生成 name->value 映射：args 声明 + 位置参数
    mapping: dict[str, str] = dict(kv)
    declared_args = list((chosen.meta or {}).get("args") or [])
    if declared_args:
        for i, name in enumerate(declared_args, start=1):
            if name and name not in mapping:
                mapping[name] = pos[i - 1] if i - 1 < len(pos) else ""

    required = list((chosen.meta or {}).get("required") or [])
    usage = str((chosen.meta or {}).get("usage") or "").strip()
    errors: list[str] = []
    for r in required:
        if not r:
            continue
        if not str(mapping.get(r, "")).strip():
            errors.append(f"缺少必填参数: {r}")

    if errors:
        if usage:
            errors.append(f"用法: /{chosen.name} {usage}")
        else:
            errors.append(f"用法提示: /{chosen.name} <args...>  （可在命令文件 frontmatter 中填写 usage）")
        return ExpandedCommand(prompt="", command=chosen, policy_overrides={}, errors=errors)

    text = chosen.template.replace("{{args}}", args_str)
    for i, a in enumerate(pos, start=1):
        text = text.replace(f"{{{{arg{i}}}}}", a)
    # 未提供的 argN 替换为空
    for i in range(len(pos) + 1, 10):
        text = text.replace(f"{{{{arg{i}}}}}", "")

    # 命名占位符
    for k, v in mapping.items():
        text = text.replace(f"{{{{{k}}}}}", v)

    expanded = text.strip()
    if not expanded:
        return None

    overrides: dict[str, Any] = {}
    if chosen.meta:
        if chosen.meta.get("allowed_tools"):
            overrides["allowed_tools"] = list(chosen.meta["allowed_tools"])
        if chosen.meta.get("disallowed_tools"):
            overrides["disallowed_tools"] = list(chosen.meta["disallowed_tools"])
        if "allow_network" in chosen.meta:
            overrides["allow_network"] = bool(chosen.meta["allow_network"])

    return ExpandedCommand(prompt=expanded, command=chosen, policy_overrides=overrides, errors=[])


