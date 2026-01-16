from __future__ import annotations

import re
from typing import TYPE_CHECKING

from clude_code.tooling.local_tools import ToolResult

if TYPE_CHECKING:
    from .agent_loop import AgentLoop


def semantic_search(loop: "AgentLoop", query: str) -> ToolResult:
    """
    执行语义搜索（向量 RAG）。

    大文件治理说明：
    - 将“向量检索/格式化结果”从编排主文件中拆出，便于独立演进与测试。
    """
    try:
        if not getattr(loop.cfg, "rag", None) or not getattr(loop.cfg.rag, "enabled", True):
            return ToolResult(False, error={"code": "E_RAG_DISABLED", "message": "RAG 已禁用（cfg.rag.enabled=false）"})

        loop.logger.debug(f"[dim]执行语义搜索: {query[:50]}...[/dim]")
        q_vector = loop.embedder.embed_query(query)
        hits = loop.vector_store.search(q_vector, limit=5)
        loop.logger.info(f"[green]✓ 语义搜索找到 {len(hits)} 个结果[/green]")

        # 业界做法：轻量 rerank（向量分数 + 元数据 + 词法信号），提升 precision 与可解释性
        q = (query or "").strip()
        q_lower = q.lower()
        ident_tokens = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", q))
        bt_tokens = set(re.findall(r"`([^`]{2,64})`", q))
        tokens = set([t.lower() for t in ident_tokens]) | set([t.strip().lower() for t in bt_tokens])

        def _boost(h: dict) -> float:
            b = 0.0
            sym = str(h.get("symbol") or "").strip().lower()
            scope = str(h.get("scope") or "").strip().lower()
            ntype = str(h.get("node_type") or "").strip().lower()
            path = str(h.get("path") or "").strip().lower()
            text = str(h.get("text") or "").strip().lower()

            # symbol/scope 命中：最有效的“符号级”信号
            if sym and (sym in tokens or sym in q_lower):
                b += 0.25
            if scope:
                for part in scope.split("/"):
                    if part and (part in tokens or part in q_lower):
                        b += 0.10
                        break

            # 定义节点优先（函数/类/类型定义通常更有信息密度）
            if any(k in ntype for k in ("function", "method", "class", "struct", "enum", "interface", "trait", "impl")):
                b += 0.08

            # path/词法弱信号：提升“用户给了文件名/模块名/关键字”的情况
            for t in list(tokens)[:8]:
                if t and t in path:
                    b += 0.06
                    break
            for t in list(tokens)[:8]:
                if t and t in text:
                    b += 0.03
                    break

            # 轻微惩罚超长块（更偏向精确召回）
            if len(text) > 5000:
                b -= 0.05
            return b

        ranked: list[dict] = []
        for h in hits:
            if not isinstance(h, dict):
                continue
            base = float(h.get("score") or 0.0)
            dist = h.get("_distance")
            try:
                dist_f = float(dist) if dist is not None else None
            except Exception:
                dist_f = None
            final = base + _boost(h)
            h2 = dict(h)
            h2["rerank_score"] = final
            if dist_f is not None:
                h2["_distance"] = dist_f
            ranked.append(h2)

        ranked.sort(key=lambda x: float(x.get("rerank_score") or 0.0), reverse=True)

        payload_hits: list[dict] = []
        for h in ranked:
            payload_hits.append(
                {
                    "path": h.get("path"),
                    "start_line": h.get("start_line"),
                    "end_line": h.get("end_line"),
                    "text": h.get("text"),
                    # 可选元数据（AST-aware chunking）
                    "language": h.get("language"),
                    "symbol": h.get("symbol"),
                    "node_type": h.get("node_type"),
                    "scope": h.get("scope"),
                    "chunk_id": h.get("chunk_id"),
                    # 分数：score=向量相似度归一化；rerank_score=融合元数据/词法后的最终分
                    "score": h.get("score"),
                    "rerank_score": h.get("rerank_score"),
                    "_distance": h.get("_distance"),
                }
            )

        return ToolResult(True, payload={"query": query, "hits": payload_hits})
    except Exception as e:
        loop.logger.error(f"[red]✗ 语义搜索失败: {e}[/red]")
        return ToolResult(False, error={"code": "E_SEMANTIC_SEARCH", "message": str(e)})


