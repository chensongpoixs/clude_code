from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class CommandDecision:
    ok: bool
    reason: str = ""


DEFAULT_DENYLIST = [
    # destructive filesystem
    r"\brm\s+-rf\b",
    r"\bdel\s+/f\b",
    r"\bformat\s+[a-z]:\b",
    r"\bmkfs\.",
    # remote fetch/exec (network)
    r"\bcurl\b",
    r"\bwget\b",
    r"\binvoke-webrequest\b",
    r"\birm\b",  # PowerShell Invoke-RestMethod alias
    # privilege escalation
    r"\bsudo\b",
]


def evaluate_command(command: str, *, allow_network: bool) -> CommandDecision:
    cmd = command.strip()
    if not cmd:
        return CommandDecision(False, "empty command")

    denylist = list(DEFAULT_DENYLIST)
    if allow_network:
        # allow network tools in general, but still keep destructive + sudo blocked
        denylist = [p for p in denylist if p not in {r"\bcurl\b", r"\bwget\b", r"\binvoke-webrequest\b", r"\birm\b"}]

    for pattern in denylist:
        if re.search(pattern, cmd, flags=re.IGNORECASE):
            return CommandDecision(False, f"command denied by policy: matched `{pattern}`")

    return CommandDecision(True, "")


