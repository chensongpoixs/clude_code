from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from clude_code.config.config import CludeConfig

# P1-1: 模块级 logger，用于调试 RAG 索引问题（默认 DEBUG 级别）
_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CodeChunk:
    text: str
    start_line: int
    end_line: int
    language: str | None = None
    symbol: str | None = None
    node_type: str | None = None
    scope: str | None = None


def detect_language_from_path(path: str) -> str | None:
    p = (path or "").lower()
    for ext, lang in (
        (".py", "python"),
        (".js", "javascript"),
        (".jsx", "javascript"),
        (".ts", "typescript"),
        (".tsx", "tsx"),
        (".go", "go"),
        (".rs", "rust"),
        (".java", "java"),
        (".c", "c"),
        (".h", "c"),
        (".cpp", "cpp"),
        (".cc", "cpp"),
        (".cxx", "cpp"),
        (".hpp", "cpp"),
    ):
        if p.endswith(ext):
            return lang
    return None


class HeuristicChunker:
    """启发式分块：按空行/上限/疑似顶层定义切分（稳定、无依赖）。"""

    def __init__(self, cfg: CludeConfig):
        self.cfg = cfg

    def chunk(self, *, text: str, path: str) -> list[CodeChunk]:
        lines = (text or "").splitlines()
        if not lines:
            return []

        target_lines = int(getattr(self.cfg.rag, "chunk_target_lines", 40) or 40)
        max_lines = int(getattr(self.cfg.rag, "chunk_max_lines", 60) or 60)
        overlap_lines = int(getattr(self.cfg.rag, "chunk_overlap_lines", 5) or 5)

        out: list[CodeChunk] = []
        cur: list[str] = []
        start = 1

        for i, line in enumerate(lines):
            cur.append(line)
            is_new_def = line.startswith(("def ", "class ", "export ", "func ", "fn "))

            should_split = False
            if len(cur) >= target_lines and not line.strip():
                should_split = True
            elif len(cur) >= max_lines:
                should_split = True
            elif len(cur) > 10 and is_new_def:
                should_split = True

            if should_split:
                out.append(
                    CodeChunk(
                        text="\n".join(cur),
                        start_line=start,
                        end_line=i + 1,
                        language=detect_language_from_path(path),
                        node_type="heuristic_block",
                    )
                )
                if overlap_lines > 0:
                    cur = cur[-overlap_lines:]
                    start = (i + 2) - len(cur)
                else:
                    cur = []
                    start = i + 2

        if cur:
            out.append(
                CodeChunk(
                    text="\n".join(cur),
                    start_line=start,
                    end_line=len(lines),
                    language=detect_language_from_path(path),
                    node_type="heuristic_block",
                )
            )
        return out


class TreeSitterChunker:
    """
    AST-aware 分块（可选依赖）：
    - 优先按函数/类/类型定义节点切分
    - 附带 symbol/node_type/scope 等元数据（用于召回解释性与 rerank）
    """

    def __init__(self, cfg: CludeConfig):
        self.cfg = cfg

    def _get_parser(self, language: str) -> Any | None:
        try:
            from tree_sitter_languages import get_parser  # type: ignore[import-not-found]
        except Exception as e:
            # P1-1: tree-sitter 未安装是可预期的，DEBUG 级别日志
            _logger.debug(f"tree_sitter_languages 未安装: {e}")
            return None
        try:
            return get_parser(language)
        except Exception as e:
            # P1-1: 语言不支持是可预期的，DEBUG 级别日志
            _logger.debug(f"tree-sitter 不支持语言 {language}: {e}")
            return None

    def chunk(self, *, text: str, path: str) -> list[CodeChunk]:
        lang = detect_language_from_path(path)
        if not lang:
            return []

        parser = self._get_parser(lang)
        if parser is None:
            return []

        src_bytes = (text or "").encode("utf-8", errors="replace")
        try:
            tree = parser.parse(src_bytes)
        except Exception as e:
            # P1-1: 解析失败可能是文件编码/语法问题，WARNING 级别日志
            _logger.warning(f"tree-sitter 解析失败 [path={path}]: {e}")
            return []

        lines = (text or "").splitlines()
        if not lines:
            return []

        min_lines = int(getattr(self.cfg.rag, "ts_min_node_lines", 6) or 6)
        max_lines = int(getattr(self.cfg.rag, "ts_max_node_lines", 220) or 220)
        lead_ctx = int(getattr(self.cfg.rag, "ts_leading_context_lines", 2) or 2)

        # 每种语言的“定义节点”集合（业界常用：符号级 chunk）
        def_nodes: dict[str, set[str]] = {
            "python": {"function_definition", "class_definition"},
            "javascript": {"function_declaration", "class_declaration", "method_definition"},
            "typescript": {"function_declaration", "class_declaration", "method_definition"},
            "tsx": {"function_declaration", "class_declaration", "method_definition"},
            # go 的 type 声明节点在不同 grammar/版本里可能叫 type_spec/type_declaration
            "go": {"function_declaration", "method_declaration", "type_spec", "type_declaration"},
            "rust": {"function_item", "struct_item", "enum_item", "impl_item", "trait_item"},
            "java": {"class_declaration", "interface_declaration", "method_declaration"},
            "c": {"function_definition", "struct_specifier", "enum_specifier", "union_specifier"},
            "cpp": {"function_definition", "struct_specifier", "class_specifier", "enum_specifier", "namespace_definition"},
        }

        targets = def_nodes.get(lang, set())
        if not targets:
            return []

        out: list[CodeChunk] = []

        def _node_text(node: Any) -> str:
            try:
                return src_bytes[node.start_byte : node.end_byte].decode("utf-8", errors="replace")
            except Exception as e:
                # P1-1: 节点文本提取失败，DEBUG 级别（常见于边界节点）
                _logger.debug(f"_node_text 失败: {e}")
                return ""

        def _node_symbol(node: Any) -> str | None:
            # tree-sitter 通常在 field "name" 上挂 identifier
            try:
                name_node = node.child_by_field_name("name")
            except Exception as e:
                _logger.debug(f"child_by_field_name('name') 失败: {e}")
                name_node = None
            if name_node is not None:
                s = _node_text(name_node).strip()
                return s or None
            # fallback：找第一个 identifier
            try:
                for ch in getattr(node, "named_children", []) or []:
                    if getattr(ch, "type", "") in {"identifier", "type_identifier"}:
                        s = _node_text(ch).strip()
                        if s:
                            return s
            except Exception as e:
                # P1-1: fallback 符号提取失败，DEBUG 级别
                _logger.debug(f"_node_symbol fallback 失败: {e}")
            return None

        def _leading_context_start(start_line: int) -> int:
            # 向上找少量“空行/注释行”
            s = start_line
            for _ in range(max(0, lead_ctx)):
                if s <= 1:
                    break
                prev = lines[s - 2].strip()
                if not prev:
                    s -= 1
                    continue
                if prev.startswith(("#", "//", "/*", "*")):
                    s -= 1
                    continue
                break
            return s

        # DFS：收集目标节点（按出现顺序）
        stack: list[tuple[Any, list[str]]] = [(tree.root_node, [])]
        while stack:
            node, scope = stack.pop()
            try:
                ntype = str(getattr(node, "type", ""))
            except Exception as e:
                # P1-1: 节点类型获取失败，DEBUG 级别
                _logger.debug(f"获取 node.type 失败: {e}")
                ntype = ""

            sym = None
            if ntype in targets:
                sym = _node_symbol(node)
                start = int(getattr(node, "start_point")[0]) + 1  # type: ignore[index]
                end = int(getattr(node, "end_point")[0]) + 1  # type: ignore[index]
                if end < start:
                    start, end = end, start
                if (end - start + 1) >= min_lines:
                    start2 = _leading_context_start(start)
                    end2 = end
                    # 过长则按启发式再切分（保持 symbol/node_type）
                    if (end2 - start2 + 1) > max_lines:
                        seg_start = start2
                        while seg_start <= end2:
                            seg_end = min(end2, seg_start + max_lines - 1)
                            seg_text = "\n".join(lines[seg_start - 1 : seg_end])
                            out.append(
                                CodeChunk(
                                    text=seg_text,
                                    start_line=seg_start,
                                    end_line=seg_end,
                                    language=lang,
                                    symbol=sym,
                                    node_type=ntype,
                                    scope="/".join(scope) if scope else None,
                                )
                            )
                            seg_start = seg_end + 1
                    else:
                        out.append(
                            CodeChunk(
                                text="\n".join(lines[start2 - 1 : end2]),
                                start_line=start2,
                                end_line=end2,
                                language=lang,
                                symbol=sym,
                                node_type=ntype,
                                scope="/".join(scope) if scope else None,
                            )
                        )

            # 子节点压栈：保持"从上到下"的顺序，需要逆序压栈
            try:
                children = list(getattr(node, "named_children", []) or [])
            except Exception as e:
                # P1-1: 子节点获取失败，DEBUG 级别
                _logger.debug(f"获取 named_children 失败: {e}")
                children = []
            # 如果当前是一个定义节点，把 symbol 加到 scope（仅当 symbol 存在）
            next_scope = list(scope)
            if ntype in targets and sym:
                next_scope = scope + [sym]
            for ch in reversed(children):
                stack.append((ch, next_scope))

        return out


def build_chunker(cfg: CludeConfig) -> Any:
    mode = str(getattr(getattr(cfg, "rag", None), "chunker", "heuristic") or "heuristic").strip().lower()
    if mode in {"tree_sitter", "treesitter", "ast"}:
        return TreeSitterChunker(cfg)
    return HeuristicChunker(cfg)


