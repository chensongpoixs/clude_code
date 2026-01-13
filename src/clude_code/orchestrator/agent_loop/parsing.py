from __future__ import annotations

import json
from typing import Any


def try_parse_tool_call(text: str) -> dict[str, Any] | None:
    """
    从 LLM 的文本输出中尝试解析工具调用 JSON。

    本函数采用多层容错策略，支持以下格式：
    1. 纯 JSON 对象：直接以 `{` 开头、`}` 结尾的文本
    2. 代码块包裹：```json ... ``` 或 ``` ... ``` 中的 JSON
    3. 最佳努力：从文本中提取第一个 `{...}` 对象

    参数:
        text: LLM 的原始输出文本（可能包含解释性文字 + JSON）

    返回:
        解析成功的工具调用字典（包含 "tool" 和 "args" 键），失败返回 None

    流程图: 见 `agent_loop_parse_tool_call_flow.svg`
    """
    text = (text or "").strip()

    candidates: list[str] = []
    if text.startswith("{") and text.endswith("}"):
        candidates.append(text)

    if "```" in text:
        for fence in ("```json", "```JSON", "```"):
            if fence in text:
                parts = text.split(fence, 1)
                if len(parts) == 2:
                    body = parts[1].split("```", 1)[0].strip()
                    if body.startswith("{") and body.endswith("}"):
                        candidates.append(body)

    if "{" in text and "}" in text:
        start = text.find("{")
        end = text.rfind("}")
        if 0 <= start < end:
            candidates.append(text[start : end + 1].strip())

    for c in candidates:
        try:
            parsed = json.loads(c)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            continue
    return None


