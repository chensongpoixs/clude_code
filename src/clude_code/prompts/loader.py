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


def render_prompt(rel_path: str, **vars: object) -> str:
    """
    渲染一个简单的 prompt 模板（不依赖第三方模板引擎）。

    支持的语法：
    - 变量替换：{{ var_name }}

    设计取舍：
    - 只做最小可控能力，避免引入 jinja2 依赖导致运行环境缺包
    - 不支持 for/if 等高级语法（如确需高级模板，再引入依赖并加可选降级）
    """
    text = read_prompt(rel_path)

    def _repl(m: re.Match[str]) -> str:
        key = m.group(1)
        val = vars.get(key, "")
        return "" if val is None else str(val)

    return _VAR_RE.sub(_repl, text)


