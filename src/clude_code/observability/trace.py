from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from clude_code.core.project_paths import ProjectPaths, DEFAULT_PROJECT_ID


@dataclass(frozen=True)
class TraceEvent:
    timestamp: int
    trace_id: str
    session_id: str
    project_id: str
    step: int
    event: str
    data: dict[str, Any]


class TraceLogger:
    """
    Verbose per-turn trace logger (JSONL).

    Writes to: {workspace_root}/.clude/projects/{project_id}/logs/trace.jsonl
    Intended for debugging "agent thinking flow" as observable steps:
    LLM output -> parsed tool call -> confirmation/policy -> tool result -> feedback.
    
    向后兼容：如果检测到旧结构（.clude/logs/），则使用旧路径。
    """

    def __init__(self, workspace_root: str, session_id: str, *, project_id: str | None = None) -> None:
        self.workspace_root = Path(workspace_root)
        self.session_id = session_id
        self.project_id = project_id or DEFAULT_PROJECT_ID
        
        # 使用 ProjectPaths 计算路径（自动检测旧结构）
        paths = ProjectPaths(workspace_root, self.project_id, auto_create=True)
        # 向后兼容：检测旧路径
        old_path = self.workspace_root / ".clude" / "logs" / "trace.jsonl"
        new_path = paths.trace_file()
        if old_path.exists() and not new_path.exists() and self.project_id == DEFAULT_PROJECT_ID:
            self._path = old_path
        else:
            self._path = new_path
            self._path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, *, trace_id: str, step: int, event: str, data: dict[str, Any]) -> None:
        ev = TraceEvent(
            timestamp=int(time.time()),
            trace_id=trace_id,
            session_id=self.session_id,
            project_id=self.project_id,
            step=step,
            event=event,
            data=data,
        )
        line = json.dumps(
            {
                "timestamp": ev.timestamp,
                "trace_id": ev.trace_id,
                "session_id": ev.session_id,
                "project_id": ev.project_id,
                "step": ev.step,
                "event": ev.event,
                "data": ev.data,
            },
            ensure_ascii=False,
        )
        with self._path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def read_traces(self, limit: int = 100, session_id: str | None = None) -> list[TraceEvent]:
        """
        读取追踪记录

        Args:
            limit: 最大记录数量
            session_id: 过滤特定会话ID

        Returns:
            追踪事件列表
        """
        if not self._path.exists():
            return []

        traces = []
        try:
            with self._path.open("r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue

                    try:
                        data = json.loads(line.strip())
                        trace_event = TraceEvent(
                            timestamp=data["timestamp"],
                            trace_id=data["trace_id"],
                            session_id=data["session_id"],
                            step=data["step"],
                            event=data["event"],
                            data=data["data"]
                        )

                        # 应用会话过滤
                        if session_id and trace_event.session_id != session_id:
                            continue

                        traces.append(trace_event)

                        # 检查是否达到限制
                        if len(traces) >= limit:
                            break

                    except json.JSONDecodeError:
                        continue  # 跳过损坏的行

        except IOError:
            return []

        # 按时间戳降序排序（最新的在前面）
        traces.sort(key=lambda t: t.timestamp, reverse=True)

        return traces

    @classmethod
    def list_sessions(cls, workspace_root: str) -> list[str]:
        """
        列出所有可用的会话ID

        Args:
            workspace_root: 工作区根目录

        Returns:
            会话ID列表
        """
        trace_path = Path(workspace_root) / ".clude" / "logs" / "trace.jsonl"
        if not trace_path.exists():
            return []

        sessions = set()
        try:
            with trace_path.open("r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue

                    try:
                        data = json.loads(line.strip())
                        sessions.add(data["session_id"])
                    except json.JSONDecodeError:
                        continue
        except IOError:
            pass

        return sorted(list(sessions))



