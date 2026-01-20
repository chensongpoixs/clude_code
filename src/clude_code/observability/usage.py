from __future__ import annotations

"""
会话用量/成本统计（轻量、无外部依赖）。

说明：
- 对本地 llama.cpp 场景，经常拿不到真实 token usage，因此这里提供“可解释的估算”。
- 估算方法默认：tokens ≈ chars / 4（英文略偏乐观，中文略偏保守，但足够做趋势/回归监控）。
"""

from dataclasses import dataclass, field
from typing import Any


def estimate_tokens(text: str) -> int:
    t = (text or "")
    # very rough heuristic; keep deterministic
    return max(1, int(len(t) / 4)) if t else 0


@dataclass
class SessionUsage:
    llm_requests: int = 0
    llm_total_ms: int = 0
    prompt_tokens_est: int = 0
    completion_tokens_est: int = 0

    tool_calls: int = 0
    tool_failures: int = 0

    by_tool: dict[str, dict[str, Any]] = field(default_factory=dict)  # name -> {calls, failures}

    def record_llm(self, *, prompt_tokens_est: int, completion_tokens_est: int, elapsed_ms: int) -> None:
        self.llm_requests += 1
        self.llm_total_ms += max(0, int(elapsed_ms))
        self.prompt_tokens_est += max(0, int(prompt_tokens_est))
        self.completion_tokens_est += max(0, int(completion_tokens_est))

    def record_tool(self, *, name: str, ok: bool) -> None:
        self.tool_calls += 1
        if not ok:
            self.tool_failures += 1
        d = self.by_tool.get(name)
        if d is None:
            d = {"calls": 0, "failures": 0}
            self.by_tool[name] = d
        d["calls"] += 1
        if not ok:
            d["failures"] += 1

    def summary(self) -> dict[str, Any]:
        return {
            "llm_requests": self.llm_requests,
            "llm_total_ms": self.llm_total_ms,
            "prompt_tokens_est": self.prompt_tokens_est,
            "completion_tokens_est": self.completion_tokens_est,
            "total_tokens_est": self.prompt_tokens_est + self.completion_tokens_est,
            "tool_calls": self.tool_calls,
            "tool_failures": self.tool_failures,
            "by_tool": self.by_tool,
        }


