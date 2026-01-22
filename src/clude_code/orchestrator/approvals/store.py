from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from clude_code.core.project_paths import ProjectPaths


ApprovalStatus = Literal["pending", "approved", "rejected"]


class ApprovalRequest(BaseModel):
    id: str = Field(..., description="审批单 ID")
    project_id: str = Field(..., description="项目 ID")
    trace_id: str = Field(..., description="trace_id")
    intent_name: str = Field("default", description="意图名")
    risk_level: str = Field("MEDIUM", description="风险等级（LOW/MEDIUM/HIGH/CRITICAL）")
    status: ApprovalStatus = Field("pending", description="审批状态")

    requested_at: float = Field(default_factory=lambda: time.time())
    decided_at: float | None = Field(default=None)
    decided_by: str | None = Field(default=None)
    comment: str | None = Field(default=None)

    plan_summary: str = Field("", description="计划摘要（短文本）")
    plan: dict[str, Any] | None = Field(default=None, description="Plan 快照（用于批准后继续执行；不包含 messages 历史）")


@dataclass
class ApprovalStore:
    workspace_root: str
    project_id: str

    def _paths(self) -> ProjectPaths:
        return ProjectPaths(self.workspace_root, self.project_id, auto_create=True)

    def create(
        self,
        *,
        trace_id: str,
        intent_name: str,
        risk_level: str,
        plan_summary: str,
        plan: dict[str, Any] | None = None,
    ) -> ApprovalRequest:
        approval_id = "apr_" + uuid.uuid4().hex[:12]
        req = ApprovalRequest(
            id=approval_id,
            project_id=self.project_id,
            trace_id=trace_id,
            intent_name=intent_name or "default",
            risk_level=risk_level or "MEDIUM",
            status="pending",
            plan_summary=plan_summary or "",
            plan=plan,
        )
        self._write(req)
        return req

    def _write(self, req: ApprovalRequest) -> None:
        p = self._paths().approval_file(req.id)
        p.write_text(req.model_dump_json(indent=2, ensure_ascii=False), encoding="utf-8")

    def get(self, approval_id: str) -> ApprovalRequest | None:
        p = self._paths().approval_file(approval_id)
        if not p.exists():
            return None
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            return ApprovalRequest.model_validate(data)
        except Exception:
            return None

    def list(self, *, status: ApprovalStatus | None = "pending", limit: int = 50) -> list[ApprovalRequest]:
        items: list[ApprovalRequest] = []
        base = self._paths().approvals_dir()
        try:
            files = sorted(base.glob("apr_*.json"), key=lambda x: x.stat().st_mtime, reverse=True)
        except Exception:
            return []

        for f in files:
            if len(items) >= max(1, int(limit)):
                break
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                req = ApprovalRequest.model_validate(data)
                if status and req.status != status:
                    continue
                items.append(req)
            except Exception:
                continue
        return items

    def approve(self, approval_id: str, *, decided_by: str = "local", comment: str = "") -> ApprovalRequest | None:
        req = self.get(approval_id)
        if not req:
            return None
        req.status = "approved"  # type: ignore[assignment]
        req.decided_at = time.time()
        req.decided_by = decided_by
        req.comment = comment or None
        self._write(req)
        return req

    def reject(self, approval_id: str, *, decided_by: str = "local", comment: str = "") -> ApprovalRequest | None:
        req = self.get(approval_id)
        if not req:
            return None
        req.status = "rejected"  # type: ignore[assignment]
        req.decided_at = time.time()
        req.decided_by = decided_by
        req.comment = comment or None
        self._write(req)
        return req


