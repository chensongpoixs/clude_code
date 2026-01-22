from __future__ import annotations

from pathlib import Path
import re


def read_prompt(rel_path: str) -> str:
    """
    从 `src/clude_code/prompts/` 读取提示词文本。

    设计目标：
    - 提示词与业务逻辑解耦，便于审计/复用/版本管理
    - 运行时不依赖包资源系统，直接从源码目录读取（对 CLI/本地运行最稳）
    """
    base = Path(__file__).resolve().parent
    p = (base / rel_path).resolve()
    # 安全护栏：只允许读取 prompts 目录内部
    if base not in p.parents and p != base:
        raise ValueError(f"prompt path escapes base: {rel_path}")
    return p.read_text(encoding="utf-8", errors="replace")


_VAR_RE = re.compile(r"\{\{\s*([a-zA-Z_]\w*)\s*\}\}")


def _strip_front_matter(text: str) -> str:
    """
    剥离 YAML front matter（顶部 `--- ... ---`），避免把元数据发给 LLM。
    """
    s = text.lstrip("\ufeff")
    if not s.startswith("---"):
        return text
    lines = s.splitlines(True)
    if not lines or lines[0].strip() != "---":
        return text
    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break
    if end_idx is None:
        return text
    body = "".join(lines[end_idx + 1 :])
    return body


def render_prompt(rel_path: str, **vars: object) -> str:
    """
    渲染一个简单的 prompt 模板（不依赖第三方模板引擎）。

    支持的语法：
    - 变量替换：{{ var_name }}

    设计取舍：
    - 只做最小可控能力，避免引入 jinja2 依赖导致运行环境缺包
    - 不支持 for/if 等高级语法（如确需高级模板，再引入依赖并加可选降级）
    """
    text = _strip_front_matter(read_prompt(rel_path))

    # Phase1：可选增强 —— 若模板包含 if/for 等语法，且环境安装了 jinja2，则使用 jinja2 渲染
    # 降级策略：无 jinja2 或渲染失败时，回退到最小变量替换（仅 {{ var }}）
    if "{%" in text:
        try:
            from jinja2 import Environment, BaseLoader, Undefined  # type: ignore

            env = Environment(loader=BaseLoader(), undefined=Undefined, autoescape=False)
            tmpl = env.from_string(text)
            return str(tmpl.render(**vars))
        except Exception:
            # 严格降级：不阻塞主流程
            pass

    def _repl(m: re.Match[str]) -> str:
        key = m.group(1)
        val = vars.get(key, "")
        return "" if val is None else str(val)

    return _VAR_RE.sub(_repl, text)


