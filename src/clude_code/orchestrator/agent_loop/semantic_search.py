from __future__ import annotations

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

        payload_hits: list[dict] = []
        for h in hits:
            payload_hits.append(
                {
                    "path": h.get("path"),
                    "start_line": h.get("start_line"),
                    "end_line": h.get("end_line"),
                    "text": h.get("text"),
                }
            )

        return ToolResult(True, payload={"query": query, "hits": payload_hits})
    except Exception as e:
        loop.logger.error(f"[red]✗ 语义搜索失败: {e}[/red]")
        return ToolResult(False, error={"code": "E_SEMANTIC_SEARCH", "message": str(e)})


