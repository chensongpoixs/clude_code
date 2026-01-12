from __future__ import annotations

import json
from typing import Any

from clude_code.tooling.local_tools import ToolResult


def _tail_lines(text: str, max_lines: int = 30, max_chars: int = 4000) -> str:
    lines = text.splitlines()
    tail = "\n".join(lines[-max_lines:])
    if len(tail) > max_chars:
        return tail[-max_chars:]
    return tail


def _head_items(items: list[dict[str, Any]], max_items: int = 20) -> list[dict[str, Any]]:
    out = []
    for it in items[:max_items]:
        out.append({k: it.get(k) for k in ("name", "is_dir", "size_bytes")})
    return out


def summarize_tool_result(tool: str, tr: ToolResult) -> dict[str, Any]:
    """
    Turn raw ToolResult into a compact, structured summary for feeding back to the LLM.
    Key idea: keep only decision-critical signals + references, avoid dumping full payload.
    """
    if not tr.ok:
        return {"tool": tool, "ok": False, "error": tr.error}

    payload = tr.payload or {}
    summary: dict[str, Any] = {"tool": tool, "ok": True}

    if tool == "list_dir":
        items = payload.get("items") or []
        if isinstance(items, list):
            dirs = sum(1 for it in items if isinstance(it, dict) and it.get("is_dir") is True)
            files = sum(1 for it in items if isinstance(it, dict) and it.get("is_dir") is False)
            summary["summary"] = {
                "path": payload.get("path"),
                "items_total": len(items),
                "dirs": dirs,
                "files": files,
                "items": _head_items([it for it in items if isinstance(it, dict)]),
                "truncated": len(items) > 20,
            }
        else:
            summary["summary"] = {"path": payload.get("path")}
        return summary

    if tool == "grep":
        hits = payload.get("hits") or []
        if isinstance(hits, list):
            head = []
            for h in hits[:20]:
                if isinstance(h, dict):
                    head.append(
                        {
                            "path": h.get("path"),
                            "line": h.get("line"),
                            "preview": (h.get("preview") or "")[:200],
                        }
                    )
            summary["summary"] = {
                "pattern": payload.get("pattern"),
                "engine": payload.get("engine", "python"),
                "hits_shown": len(head),
                "hits_total": len(hits),
                "truncated": bool(payload.get("truncated", False)) or len(hits) > 20,
                "hits": head,
            }
        else:
            summary["summary"] = {"pattern": payload.get("pattern")}
        return summary

    if tool == "read_file":
        text = str(payload.get("text") or "")
        summary["summary"] = {
            "path": payload.get("path"),
            "offset": payload.get("offset"),
            "limit": payload.get("limit"),
            "chars": len(text),
            "text_head": text[:800],
            "text_tail": _tail_lines(text, max_lines=15, max_chars=1200),
            "truncated": len(text) > 2000,
        }
        return summary

    if tool == "run_cmd":
        out = str(payload.get("output") or "")
        summary["summary"] = {
            "command": payload.get("command"),
            "cwd": payload.get("cwd"),
            "exit_code": payload.get("exit_code"),
            "output_tail": _tail_lines(out, max_lines=40, max_chars=3000),
            "output_chars": len(out),
            "truncated": len(out) > 3000,
        }
        return summary

    if tool in {"apply_patch", "undo_patch"}:
        # These already contain compact, high-signal fields.
        keep = {
            k: payload.get(k)
            for k in (
                "path",
                "undo_id",
                "mode",
                "replacements",
                "expected_replacements",
                "fuzzy",
                "min_similarity",
                "matched_similarity",
                "before_hash",
                "after_hash",
                "restored_hash",
                "current_hash_before_restore",
            )
            if k in payload
        }
        summary["summary"] = keep
        return summary

    # default: pass a small view
    summary["summary"] = {"keys": sorted(list(payload.keys()))[:30]}
    return summary


def format_feedback_message(tool: str, tr: ToolResult) -> str:
    """
    JSON string fed back to the model as a user message.
    Must remain compact and structured.
    """
    return json.dumps(summarize_tool_result(tool, tr), ensure_ascii=False)


