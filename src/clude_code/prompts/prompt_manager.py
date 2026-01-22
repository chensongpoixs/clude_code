"""
@author chensong
@date 2026-01-22
@brief Prompt 三层继承与版本体系（Prompt Manager，遵循企业增强版 3.3）

功能说明（What & Why）：
- 为“合并型 Agent（企业落地增强版）”提供可组合、可版本化、可回滚的 Prompt 组织能力。
- 支持 Base / Domain / Task 三层组合，解析 YAML front matter 元数据，并渲染 {{ var }} 变量。
- 目标是三层继承+版本化+回滚指针，同时 **不影响现有 prompt（向后兼容）**：
  - 当三层 prompt 不存在/配置缺失时，调用方应回退到原有 `agent_loop/*.md|*.j2` 提示词。

执行流程（Flow）：
- 1) 解析 Prompt 文件（可选 front matter） -> (meta, body)
- 2) 若指定 version：优先解析 *_v{version}.(md|j2) 文件；失败回退默认文件
- 3) 拼接 base/domain/task 文本
- 4) 对拼接后的文本进行 {{ var }} 替换渲染

注意事项（Notes）：
- Phase 1 只支持“精确版本号”（如 1.2.3），不解析 ^/~ 范围（后续可扩展）。
- 解析失败必须降级：返回空文本 + 记录 warning（不阻塞主流程）。
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_logger = logging.getLogger(__name__)

_VAR_RE = re.compile(r"\{\{\s*([a-zA-Z_]\w*)\s*\}\}")


@dataclass(frozen=True)
class PromptArtifact:
    ref: str
    path: Path
    meta: dict[str, Any]
    body: str


def _render_text(text: str, **vars: object) -> str:
    def _repl(m: re.Match[str]) -> str:
        key = m.group(1)
        val = vars.get(key, "")
        return "" if val is None else str(val)

    return _VAR_RE.sub(_repl, text)


def _split_front_matter(text: str) -> tuple[dict[str, Any], str]:
    """
    解析 YAML front matter（仅支持最常见的 `--- ... ---` 顶部块）。
    返回: (meta, body)
    """
    s = text.lstrip("\ufeff")  # remove BOM
    if not s.startswith("---"):
        return {}, text

    # 找第二个 --- 行作为结束
    # 允许 \r\n / \n
    m = re.search(r"^---\s*$", s, flags=re.MULTILINE)
    if not m:
        return {}, text

    # 找到第二个分隔线
    # 第一行是 ---，因此从下一行开始找
    lines = s.splitlines(True)
    if not lines or not lines[0].strip().startswith("---"):
        return {}, text

    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break
    if end_idx is None:
        return {}, text

    head = "".join(lines[1:end_idx])
    body = "".join(lines[end_idx + 1 :])

    # 延迟 import：避免强依赖
    try:
        import yaml  # type: ignore

        meta = yaml.safe_load(head) or {}
        if not isinstance(meta, dict):
            meta = {}
        return meta, body
    except Exception as e:
        _logger.warning(f"[PromptManager] front matter 解析失败，已忽略: {e}")
        return {}, body


def _resolve_versioned_ref(ref: str, version: str | None) -> str:
    """
    将 ref + version 映射为版本化文件名：
    - foo/bar.j2 + 1.2.3 => foo/bar_v1.2.3.j2
    """
    if not version:
        return ref
    p = Path(ref)
    stem = p.stem
    suffix = "".join(p.suffixes) or ""
    if suffix:
        return str(p.with_name(f"{stem}_v{version}{suffix}"))
    # 无后缀：默认当作 .md
    return str(p.with_name(f"{stem}_v{version}.md"))


class PromptManager:
    """
    PromptManager：三层组合 + 版本选择 + 元数据解析。
    """

    def __init__(self, *, workspace_root: str | None = None) -> None:
        self._prompts_root = Path(__file__).resolve().parent
        self._workspace_root = workspace_root

    def _read_rel(self, rel_path: str) -> str:
        base = self._prompts_root
        p = (base / rel_path).resolve()
        if base not in p.parents and p != base:
            raise ValueError(f"prompt path escapes base: {rel_path}")
        return p.read_text(encoding="utf-8", errors="replace")

    def _try_load(self, ref: str) -> PromptArtifact | None:
        try:
            txt = self._read_rel(ref)
            meta, body = _split_front_matter(txt)
            return PromptArtifact(ref=ref, path=(self._prompts_root / ref).resolve(), meta=meta, body=body)
        except FileNotFoundError:
            return None
        except Exception as e:
            _logger.warning(f"[PromptManager] 读取失败: ref={ref} err={e}")
            return None

    def load(self, ref: str, *, version: str | None = None) -> PromptArtifact | None:
        """
        加载 Prompt（支持版本化文件名回退）。
        """
        if not ref:
            return None
        ref = str(ref).strip()
        if not ref:
            return None

        # 1) 版本选择：显式 version > 回滚指针 current > 默认 ref
        chosen_version = version or self.get_current_version(ref)
        if chosen_version:
            vref = _resolve_versioned_ref(ref, chosen_version)
            art = self._try_load(vref)
            if art is not None:
                return art

        # 2) 回退默认 ref
        return self._try_load(ref)

    def _merge_meta(self, metas: list[dict[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        # 简单覆盖 + 列表去重合并
        list_keys = {"tools_expected", "constraints"}
        for m in metas:
            if not isinstance(m, dict):
                continue
            for k, v in m.items():
                if k in list_keys:
                    prev = out.get(k) or []
                    if not isinstance(prev, list):
                        prev = []
                    if isinstance(v, list):
                        merged = list(dict.fromkeys([*prev, *v]))
                        out[k] = merged
                    else:
                        out[k] = prev
                else:
                    out[k] = v
        return out

    def compose(
        self,
        *,
        base_ref: str | None = None,
        domain_ref: str | None = None,
        task_ref: str | None = None,
        base_version: str | None = None,
        domain_version: str | None = None,
        task_version: str | None = None,
        vars: dict[str, object] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """
        组合三层 Prompt，并返回 (rendered_text, merged_meta)。
        """
        vars = vars or {}

        base_art = self.load(base_ref or "", version=base_version) if base_ref else None
        domain_art = self.load(domain_ref or "", version=domain_version) if domain_ref else None
        task_art = self.load(task_ref or "", version=task_version) if task_ref else None

        metas = [a.meta for a in [base_art, domain_art, task_art] if a is not None]
        merged_meta = self._merge_meta(metas)

        parts: list[str] = []
        if base_art and base_art.body.strip():
            parts.append(base_art.body.strip())
        if domain_art and domain_art.body.strip():
            parts.append(domain_art.body.strip())
        if task_art and task_art.body.strip():
            parts.append(task_art.body.strip())

        raw = "\n\n".join(parts).strip()
        if not raw:
            return "", merged_meta

        rendered = _render_text(raw, **vars)
        return rendered.strip(), merged_meta

    # ====== 版本回滚指针（current -> previous） ======

    def _versions_file(self) -> Path | None:
        if not self._workspace_root:
            return None
        try:
            from clude_code.core.project_paths import ProjectPaths

            return ProjectPaths(self._workspace_root).prompt_versions_file(scope="global")
        except Exception:
            # 兜底：避免在极端环境下 import 失败阻塞主流程
            return Path(self._workspace_root) / ".clude" / "registry" / "prompt_versions.json"

    def _read_versions(self) -> dict[str, Any]:
        p = self._versions_file()
        if not p or not p.exists():
            return {"prompts": {}}
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
            if not isinstance(obj, dict):
                return {"prompts": {}}
            if "prompts" not in obj or not isinstance(obj.get("prompts"), dict):
                obj["prompts"] = {}
            return obj
        except Exception:
            return {"prompts": {}}

    def _write_versions(self, obj: dict[str, Any]) -> None:
        p = self._versions_file()
        if not p:
            return
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            # 不阻塞主流程
            return

    def get_current_version(self, ref: str) -> str | None:
        """
        获取 prompt 的 current 版本（回滚指针）。
        """
        ref = str(ref or "").strip()
        if not ref:
            return None
        obj = self._read_versions()
        it = (obj.get("prompts") or {}).get(ref) or {}
        v = it.get("current")
        return str(v).strip() if v else None

    def set_current_version(self, ref: str, new_version: str) -> None:
        """
        设置 current 版本，同时把旧 current 写入 previous（用于回滚）。
        """
        ref = str(ref or "").strip()
        new_version = str(new_version or "").strip()
        if not ref or not new_version:
            return
        obj = self._read_versions()
        prompts = obj.setdefault("prompts", {})
        it = prompts.get(ref) or {}
        cur = it.get("current")
        if cur and str(cur).strip() != new_version:
            it["previous"] = str(cur).strip()
        it["current"] = new_version
        prompts[ref] = it
        self._write_versions(obj)


