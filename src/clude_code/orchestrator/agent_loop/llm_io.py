from __future__ import annotations

import json
from typing import Any, Callable, TYPE_CHECKING

from clude_code.llm.llama_cpp_http import ChatMessage

if TYPE_CHECKING:
    from .agent_loop import AgentLoop


def normalize_messages_for_llama(
    loop: "AgentLoop",
    stage: str,
    *,
    step_id: str | None = None,
    _ev: Callable[[str, dict[str, Any]], None] | None = None,
) -> None:
    """
    发送给 llama.cpp 前的“统一出口”规范化：
    - 合并连续的 user/user 或 assistant/assistant（避免 chat template 报 500）
    - 合并多条 system 到第一条 system（避免 system/system 或 system 插入导致不交替）
    - 如果 system 后意外出现 assistant，则并入 system（保持严格 alternation）
    """
    if not loop.messages:
        return

    original_len = len(loop.messages)
    merged_pairs = 0
    merged_system = 0
    merged_into_system_from_assistant = 0

    system_msg: ChatMessage | None = None
    idx = 0
    if loop.messages[0].role == "system":
        system_msg = loop.messages[0]
        idx = 1

    out: list[ChatMessage] = []
    if system_msg is not None:
        out.append(system_msg)

    expected = "user"

    for m in loop.messages[idx:]:
        role = m.role
        content = m.content

        if role == "system":
            if out and out[0].role == "system":
                merged_system += 1
                out[0] = ChatMessage(role="system", content=out[0].content + "\n\n" + content)
                continue
            out.insert(0, m)
            continue

        if expected == "user" and (not out or out[-1].role == "system") and role == "assistant":
            if out and out[0].role == "system":
                merged_into_system_from_assistant += 1
                out[0] = ChatMessage(role="system", content=out[0].content + "\n\n" + "[历史 assistant 前置信息]\n" + content)
                continue
            merged_pairs += 1
            continue

        if role == expected:
            out.append(m)
            expected = "assistant" if expected == "user" else "user"
            continue

        if out and out[-1].role == role:
            merged_pairs += 1
            out[-1] = ChatMessage(role=role, content=out[-1].content + "\n\n" + content)
            continue

        if out:
            merged_pairs += 1
            out[-1] = ChatMessage(role=out[-1].role, content=out[-1].content + "\n\n" + content)
            continue

    if len(out) != original_len or merged_pairs or merged_system or merged_into_system_from_assistant:
        loop.messages = out
        loop._trim_history(max_messages=30)
        if _ev:
            _ev(
                "messages_normalized",
                {
                    "stage": stage,
                    "step_id": step_id,
                    "before": original_len,
                    "after": len(loop.messages),
                    "merged_pairs": merged_pairs,
                    "merged_system": merged_system,
                    "merged_assistant_into_system": merged_into_system_from_assistant,
                },
            )


def llm_chat(
    loop: "AgentLoop",
    stage: str,
    *,
    step_id: str | None = None,
    _ev: Callable[[str, dict[str, Any]], None] | None = None,
) -> str:
    """
    llama.cpp 调用统一出口：先做 messages 规范化，再发起 HTTP 请求。

    业界做法：
    - 统一出口处打印/落盘“请求参数 + 请求数据摘要 + 返回数据摘要”，便于复盘 400/500/超时问题。
    - 避免在多个调用点各自打印造成遗漏或输出不一致。
    """
    normalize_messages_for_llama(loop, stage, step_id=step_id, _ev=_ev)

    # 1) 记录/打印请求参数（model 等）与请求数据摘要
    try:
        req_obj = {
            "stage": stage,
            "step_id": step_id,
            "base_url": loop.llm.base_url,
            "api_mode": loop.llm.api_mode,
            "model": loop.llm.model or "auto",
            "temperature": loop.llm.temperature,
            "max_tokens": loop.llm.max_tokens,
            "messages_count": len(loop.messages),
            "last_role": loop.messages[-1].role if loop.messages else None,
            "last_content_preview": (loop.messages[-1].content[:200] + "…") if (loop.messages and len(loop.messages[-1].content) > 200) else (loop.messages[-1].content if loop.messages else None),
        }
        # 写入文件（详细）
        log_llm_request_params_to_file(loop)
        # 控制台/trace（摘要）
        if _ev:
            _ev("llm_request_params", req_obj)
        loop.logger.info(f"[dim]LLM 请求参数: model={req_obj['model']} api_mode={req_obj['api_mode']} messages={req_obj['messages_count']}[/dim]")
    except Exception:
        # 打印失败不影响主流程
        pass

    # 2) 发起请求
    assistant_text = loop.llm.chat(loop.messages)

    # 3) 记录/打印返回数据摘要（不依赖 tool_call，tool_call 在上层解析后另行落盘）
    try:
        resp_obj = {
            "stage": stage,
            "step_id": step_id,
            "text_length": len(assistant_text),
            "text_preview": assistant_text,
        }
        log_llm_response_data_to_file(loop, assistant_text, tool_call=None)
        if _ev:
            _ev("llm_response_data", resp_obj)
        loop.logger.info(f"[dim]LLM 返回摘要: text_length={resp_obj['text_length']}[/dim]")
    except Exception as ex:
        loop.file_only_logger.warning(f"LLM 响应后处理异常: {ex}", exc_info=True)

    return assistant_text


def log_llm_request_params_to_file(loop: "AgentLoop") -> None:
    """把本次 LLM 请求参数（含 messages 摘要）写入 file_only_logger。"""
    request_params = {
        "model": loop.llm.model,
        "temperature": loop.llm.temperature,
        "max_tokens": loop.llm.max_tokens,
        "api_mode": loop.llm.api_mode,
        "base_url": loop.llm.base_url,
        "messages_count": len(loop.messages),
        "messages": [
            {
                "role": msg.role,
                "content_preview": msg.content,
                "content_length": len(msg.content),
            }
            for msg in loop.messages
        ],
    }
    loop.file_only_logger.info(f"请求大模型参数: {json.dumps(request_params, ensure_ascii=False, indent=2)}")


def log_llm_response_data_to_file(loop: "AgentLoop", assistant_text: str, tool_call: dict[str, Any] | None) -> None:
    """把本次 LLM 返回数据摘要写入 file_only_logger。"""
    response_data = {
        "text_length": len(assistant_text),
        "text_preview":   assistant_text,
        "truncated": len(assistant_text) > 500,
        "has_tool_call": tool_call is not None,
        "tool_call": tool_call if tool_call else None,
    }
    loop.file_only_logger.info(f"大模型返回数据: {json.dumps(response_data, ensure_ascii=False, indent=2)}")


