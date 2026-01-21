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


def summarize_tool_result(tool: str, tr: ToolResult, keywords: set[str] | None = None) -> dict[str, Any]:
    """
    Turn raw ToolResult into a compact, structured summary for feeding back to the LLM.
    Key idea: keep only decision-critical signals + references, avoid dumping full payload.
    """
    if not tr.ok:
        return {"tool": tool, "ok": False, "error": tr.error}

    payload = tr.payload or {}
    summary: dict[str, Any] = {"tool": tool, "ok": True}
    
    # --- Phase 2: Add verification error if present ---
    if "verification_error" in payload:
        summary["verification_error"] = payload["verification_error"]

    # Pre-process keywords for search
    kw_list = [k.lower() for k in (keywords or []) if k]

    # 全局护栏：回喂给 LLM 的摘要必须有上限（防止上下文膨胀/刷屏）
    MAX_PREVIEW_CHARS = 200
    MAX_GREP_HITS = 20
    MAX_READ_FILE_CHARS = 4000
    MAX_WEB_RESULTS = 5
    MAX_CODE_RESULTS = 5
    MAX_WEBFETCH_PREVIEW_CHARS = 800

    if tool == "list_dir":
        # ... (list_dir logic remains same as it's already compact)
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
        # ... (grep logic)
        hits = payload.get("hits") or []
        if isinstance(hits, list):
            head = []
            # Prioritize hits that match keywords
            prioritized = []
            others = []
            for h in hits:
                preview = (h.get("preview") or "").lower()
                if any(kw in preview for kw in kw_list):
                    prioritized.append(h)
                else:
                    others.append(h)
            
            combined = (prioritized + others)[:MAX_GREP_HITS]
            for h in combined:
                if isinstance(h, dict):
                    head.append(
                        {
                            "path": h.get("path"),
                            "line": h.get("line"),
                            "preview": (h.get("preview") or "")[:MAX_PREVIEW_CHARS],
                        }
                    )
            summary["summary"] = {
                "pattern": payload.get("pattern"),
                "engine": payload.get("engine", "python"),
                "hits_shown": len(head),
                "hits_total": len(hits),
                "truncated": bool(payload.get("truncated", False)) or len(hits) > MAX_GREP_HITS,
                "hits": head,
            }
        else:
            summary["summary"] = {"pattern": payload.get("pattern")}
        return summary

    if tool == "read_file":
        text = str(payload.get("text") or "")
        lines = text.splitlines()
        
        # Semantic Window Sampling: Balanced for depth & token economy
        windows = []
        if kw_list:
            for i, line in enumerate(lines):
                # Detect logical flow keywords even if they aren't user keywords
                is_logic_anchor = any(anchor in line.lower() for anchor in ["if ", "for ", "while ", "try:", "return ", "class ", "def "])
                is_user_hit = any(kw in line.lower() for kw in kw_list)
                
                if is_user_hit:
                    # Give user hit more context
                    start = max(0, i - 10)
                    end = min(len(lines), i + 11)
                    windows.append((start, end))
                elif is_logic_anchor and len(kw_list) > 0:
                    # Keep logic flow near user hits
                    start = max(0, i - 2)
                    end = min(len(lines), i + 3)
                    windows.append((start, end))
        
        # Merge overlapping windows
        merged = []
        if windows:
            windows.sort()
            curr_s, curr_e = windows[0]
            for next_s, next_e in windows[1:]:
                if next_s <= curr_e:
                    curr_e = max(curr_e, next_e)
                else:
                    merged.append((curr_s, curr_e))
                    curr_s, curr_e = next_s, next_e
            merged.append((curr_s, curr_e))
        
        sampled_text = ""
        if merged:
            sampled_parts = []
            for s, e in merged:
                sampled_parts.append(f"--- lines {s+1}-{e} ---\n" + "\n".join(lines[s:e]))
            sampled_text = "\n\n".join(sampled_parts)
        
        if not sampled_text:
            # Fallback to head/tail if no keywords matched
            sampled_text = text[:800] + "\n...[gap]...\n" + _tail_lines(text, max_lines=15, max_chars=1200)

        # 最终护栏：避免极端窗口合并导致 sampled_text 仍然过大
        if len(sampled_text) > MAX_READ_FILE_CHARS:
            sampled_text = sampled_text[:MAX_READ_FILE_CHARS] + "\n...(内容已截断)\n"
        summary["summary"] = {
            "path": payload.get("path"),
            "offset": payload.get("offset"),
            "limit": payload.get("limit"),
            "chars_total": len(text),
            "content": sampled_text,
            "truncated": len(text) > len(sampled_text) or len(text) > MAX_READ_FILE_CHARS,
        }
        return summary

    # ... (rest of the logic)

    if tool == "glob_file_search":
        matches = payload.get("matches") or []
        summary["summary"] = {
            "pattern": payload.get("pattern"),
            "matches_total": len(matches),
            "matches": matches[:50],  # Give a good chunk for selection
            "truncated": len(matches) > 50,
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

    if tool == "search_semantic":
        hits = payload.get("hits") or []
        summary["summary"] = {
            "query": payload.get("query"),
            "hits_total": len(hits),
            "hits": [
                {
                    "path": h.get("path"),
                    "lines": f"{h.get('start_line')}-{h.get('end_line')}",
                    "preview": (h.get("text") or "")[:MAX_PREVIEW_CHARS]
                }
                for h in hits[:5]
            ]
        }
        return summary

    if tool == "codesearch":
        results = payload.get("results") or []
        provider = payload.get("provider")
        out_items = []
        if isinstance(results, list):
            for r in results[:MAX_CODE_RESULTS]:
                if not isinstance(r, dict):
                    continue
                code = str(r.get("code") or "")
                out_items.append(
                    {
                        "repo": r.get("repo"),
                        "path": r.get("path"),
                        "language": r.get("language"),
                        "preview": code[:MAX_PREVIEW_CHARS],
                        "url": r.get("url"),
                    }
                )
        summary["summary"] = {
            "provider": provider,
            "query": payload.get("query"),
            "results_total": (len(results) if isinstance(results, list) else 0),
            "results": out_items,
        }
        return summary

    if tool == "websearch":
        results = payload.get("results") or []
        out_items = []
        if isinstance(results, list):
            for r in results[:MAX_WEB_RESULTS]:
                if not isinstance(r, dict):
                    continue
                out_items.append(
                    {
                        "title": r.get("title"),
                        "url": r.get("url"),
                        "snippet": (str(r.get("snippet") or "")[:MAX_PREVIEW_CHARS]),
                    }
                )
        summary["summary"] = {
            "provider": payload.get("provider"),
            "query": payload.get("query"),
            "results_total": (len(results) if isinstance(results, list) else 0),
            "results": out_items,
        }
        return summary

    if tool == "webfetch":
        content = str(payload.get("content") or "")
        summary["summary"] = {
            "url": payload.get("url"),
            "title": payload.get("title"),
            "format": payload.get("format"),
            "status_code": payload.get("status_code"),
            "content_length": payload.get("content_length"),
            "truncated": bool(payload.get("truncated", False)),
            "from_cache": bool(payload.get("from_cache", False)),
            "cache_file": payload.get("cache_file") if payload.get("from_cache") else None,
            "expires_at": payload.get("expires_at"),
            "content_preview": content[:MAX_WEBFETCH_PREVIEW_CHARS],
        }
        return summary

    if tool == "write_file":
        summary["summary"] = {
            "path": payload.get("path"),
            "action": payload.get("action"),
            "bytes_written": payload.get("bytes_written"),
        }
        return summary

    #  extension: wearther_tool
    if  tool == "weather_tool":
        weather_info = payload.get("weather_info") or {}
        summary["summary"] = {
            "location": weather_info.get("location"),
            "temperature": weather_info.get("temperature"),
            "condition": weather_info.get("condition"),
            "humidity": weather_info.get("humidity"),
        }
        return summary
    # extension: get_weather
    # extract full payload for get_weather tool
    if tool in {"display", "preview_multi_edit", "question", "load_skill", "todowrite", "todoread",
"run_task", "get_task_status", "get_weather", "get_weather_forecast"}:
        return payload
    # if tool == "get_weather_forecast":
    #     return payload;
    # default: pass a small view
    summary["summary"] = {"keys": sorted(list(payload.keys()))[:30]}
    return summary


def format_feedback_message(tool: str, tr: ToolResult, keywords: set[str] | None = None) -> str:
    """
    JSON string fed back to the model as a user message.
    Must remain compact and structured.
    """
    return json.dumps(summarize_tool_result(tool, tr, keywords=keywords), ensure_ascii=False)


