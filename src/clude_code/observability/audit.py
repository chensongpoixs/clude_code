from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AuditEvent:
    timestamp: int
    trace_id: str
    session_id: str
    event: str
    data: dict[str, Any]


class AuditLogger:
    """
    Minimal JSONL audit logger.

    Writes to: {workspace_root}/.clude/logs/audit.jsonl
    """

    def __init__(self, workspace_root: str, session_id: str) -> None:
        self.workspace_root = Path(workspace_root)
        self.session_id = session_id
        self._path = self.workspace_root / ".clude" / "logs" / "audit.jsonl"
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, *, trace_id: str, event: str, data: dict[str, Any]) -> None:
        ev = AuditEvent(
            timestamp=int(time.time()),
            trace_id=trace_id,
            session_id=self.session_id,
            event=event,
            data=data,
        )
        line = json.dumps(
            {
                "timestamp": ev.timestamp,
                "trace_id": ev.trace_id,
                "session_id": ev.session_id,
                "event": ev.event,
                "data": ev.data,
            },
            ensure_ascii=False,
        )
        with self._path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")


