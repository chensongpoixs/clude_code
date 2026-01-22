from __future__ import annotations

import base64
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from clude_code.core.project_paths import ProjectPaths, DEFAULT_PROJECT_ID
from clude_code.config.config import AuditSecurityConfig


@dataclass(frozen=True)
class AuditEvent:
    timestamp: int
    trace_id: str
    session_id: str
    project_id: str
    event: str
    data: dict[str, Any]


class AuditLogger:
    """
    Minimal JSONL audit logger.

    Writes to: {workspace_root}/.clude/projects/{project_id}/logs/audit.jsonl
    
    向后兼容：如果检测到旧结构（.clude/logs/），则使用旧路径。
    """

    def __init__(
        self,
        workspace_root: str,
        session_id: str,
        *,
        project_id: str | None = None,
        security: AuditSecurityConfig | None = None,
    ) -> None:
        self.workspace_root = Path(workspace_root)
        self.session_id = session_id
        self.project_id = project_id or DEFAULT_PROJECT_ID
        self.security = security or AuditSecurityConfig()
        
        # 使用 ProjectPaths 计算路径（自动检测旧结构）
        paths = ProjectPaths(workspace_root, self.project_id, auto_create=True)
        # 向后兼容：检测旧路径
        old_path = self.workspace_root / ".clude" / "logs" / "audit.jsonl"
        new_path = paths.audit_file()
        if old_path.exists() and not new_path.exists() and self.project_id == DEFAULT_PROJECT_ID:
            self._path = old_path
        else:
            self._path = new_path
            self._path.parent.mkdir(parents=True, exist_ok=True)

    def _redact_any(self, obj: Any) -> Any:
        if not self.security.redact_enabled:
            return obj

        keys_lc = {k.lower() for k in (self.security.redact_keys or [])}

        def _redact_text(s: str) -> str:
            if not self.security.redact_text_enabled:
                return s
            # Bearer token
            s = re.sub(r"(?i)\bBearer\s+([A-Za-z0-9\-\._~\+/]+=*)", "Bearer ******", s)
            # OpenAI-like keys: sk-...
            s = re.sub(r"\bsk-[A-Za-z0-9]{10,}\b", "sk-******", s)
            return s

        if isinstance(obj, dict):
            out: dict[str, Any] = {}
            for k, v in obj.items():
                if isinstance(k, str) and k.lower() in keys_lc:
                    out[k] = "******"
                else:
                    out[k] = self._redact_any(v)
            return out
        if isinstance(obj, list):
            return [self._redact_any(x) for x in obj]
        if isinstance(obj, tuple):
            return tuple(self._redact_any(x) for x in obj)
        if isinstance(obj, str):
            return _redact_text(obj)
        return obj

    def _try_encrypt_data(self, data_obj: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        """
        返回 (enc_payload_or_none, error_message)。
        enc_payload 示例：{"alg":"AESGCM","kid":"...","nonce_b64":"...","ciphertext_b64":"..."}
        """
        if not self.security.encrypt_enabled:
            return None, ""

        key_b64 = os.environ.get(self.security.encrypt_key_env, "").strip()
        if not key_b64:
            return None, f"missing_key_env:{self.security.encrypt_key_env}"

        try:
            key = base64.b64decode(key_b64, validate=False)
        except Exception as e:
            return None, f"bad_key_b64:{type(e).__name__}"

        if len(key) not in (16, 24, 32):
            return None, f"bad_key_len:{len(key)}"

        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # type: ignore
        except Exception as e:
            return None, f"dep_missing:cryptography:{type(e).__name__}"

        try:
            nonce = os.urandom(12)
            aes = AESGCM(key)
            plaintext = json.dumps(data_obj, ensure_ascii=False).encode("utf-8")
            ct = aes.encrypt(nonce, plaintext, None)
            return (
                {
                    "alg": "AESGCM",
                    "kid": self.security.encrypt_kid,
                    "nonce_b64": base64.b64encode(nonce).decode("ascii"),
                    "ciphertext_b64": base64.b64encode(ct).decode("ascii"),
                },
                "",
            )
        except Exception as e:
            return None, f"encrypt_failed:{type(e).__name__}:{e}"

    def write(self, *, trace_id: str, event: str, data: dict[str, Any]) -> None:
        safe_data = self._redact_any(data)

        ev = AuditEvent(
            timestamp=int(time.time()),
            trace_id=trace_id,
            session_id=self.session_id,
            project_id=self.project_id,
            event=event,
            data=safe_data,
        )
        payload: dict[str, Any] = {
            "timestamp": ev.timestamp,
            "trace_id": ev.trace_id,
            "session_id": ev.session_id,
            "project_id": ev.project_id,
            "event": ev.event,
        }

        enc, enc_err = self._try_encrypt_data(ev.data)
        if enc is not None:
            payload["data_enc"] = enc
        else:
            if self.security.encrypt_enabled and enc_err and self.security.encrypt_fail_closed:
                raise RuntimeError(f"audit_encrypt_failed: {enc_err}")
            payload["data"] = ev.data
            if self.security.encrypt_enabled and enc_err:
                payload["encrypt_warning"] = enc_err

        line = json.dumps(payload, ensure_ascii=False)
        with self._path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")


