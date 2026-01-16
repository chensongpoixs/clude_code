from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from clude_code.llm.llama_cpp_http import ChatMessage


@dataclass(frozen=True)
class SessionLoadResult:
    session_id: str
    history: list[ChatMessage]  # 不含 system
    meta: dict[str, Any]


def _sessions_dir(workspace_root: str) -> Path:
    return Path(workspace_root) / ".clude" / "sessions"


def save_session(
    *,
    workspace_root: str,
    session_id: str,
    messages: list[ChatMessage],
    last_trace_id: str | None,
) -> Path:
    """
    保存会话（只保存 history，不保存 system）。

    说明：
    - system prompt 会动态包含 repo map / CLAUDE.md，恢复时应以“当前仓库最新状态”为准；
      因此只保存非 system 的历史对话，恢复时追加到新 system 之后。
    """
    d = _sessions_dir(workspace_root)
    d.mkdir(parents=True, exist_ok=True)

    history = [{"role": m.role, "content": m.content} for m in (messages[1:] if len(messages) > 0 else [])]
    now = int(time.time())
    obj: dict[str, Any] = {
        "version": 1,
        "session_id": session_id,
        "updated_at": now,
        "last_trace_id": last_trace_id,
        "history": history,
    }

    p = d / f"{session_id}.json"
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

    latest = d / "latest.json"
    latest.write_text(
        json.dumps({"session_id": session_id, "updated_at": now, "path": str(p.name)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return p


def load_latest_session(workspace_root: str) -> SessionLoadResult | None:
    d = _sessions_dir(workspace_root)
    latest = d / "latest.json"
    if latest.exists():
        try:
            data = json.loads(latest.read_text(encoding="utf-8"))
            sid = str(data.get("session_id", "")).strip()
            if sid:
                return load_session(workspace_root, sid)
        except Exception:
            pass

    if not d.exists():
        return None
    # fallback：找最后修改的 session 文件
    candidates = sorted([p for p in d.glob("*.json") if p.name != "latest.json"], key=lambda p: p.stat().st_mtime, reverse=True)
    for p in candidates:
        sid = p.stem
        r = load_session(workspace_root, sid)
        if r is not None:
            return r
    return None


def load_session(workspace_root: str, session_id: str) -> SessionLoadResult | None:
    d = _sessions_dir(workspace_root)
    p = d / f"{session_id}.json"
    if not p.exists():
        return None
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
        hist = obj.get("history") or []
        history: list[ChatMessage] = []
        if isinstance(hist, list):
            for it in hist:
                if not isinstance(it, dict):
                    continue
                role = str(it.get("role", "")).strip()
                content = str(it.get("content", ""))
                if role in {"user", "assistant"}:
                    history.append(ChatMessage(role=role, content=content))
        meta: dict[str, Any] = {k: v for k, v in obj.items() if k not in {"history"}}
        return SessionLoadResult(session_id=session_id, history=history, meta=meta)
    except Exception:
        return None


