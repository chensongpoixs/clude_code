from __future__ import annotations

import json
import inspect
import time
from typing import Any, Callable, TYPE_CHECKING

from clude_code.llm.llama_cpp_http import ChatMessage
from clude_code.observability.usage import estimate_tokens

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
    发送给 llama.cpp 前的"统一出口"规范化：
    - 确保消息角色严格交替：user/assistant/user/assistant/...（避免 chat template 报 500）
    - 保留最新的system消息
    - 合并连续相同角色的消息
    """
    if not loop.messages:
        return

    original_len = len(loop.messages)

    # 第一遍：保留system消息和最新的消息
    filtered: list[ChatMessage] = []
    last_system: ChatMessage | None = None

    for msg in loop.messages:
        if msg.role == "system":
            last_system = msg
        else:
            filtered.append(msg)

    # 如果有system消息，插入到开头
    if last_system:
        filtered.insert(0, last_system)

    # 第二遍：确保角色交替，合并连续相同角色
    normalized: list[ChatMessage] = []
    last_role = None

    for msg in filtered:
        if not normalized:
            # 第一条消息直接添加
            normalized.append(msg)
            last_role = msg.role
        elif msg.role == last_role:
            # 连续相同角色，合并内容
            normalized[-1] = ChatMessage(
                role=last_role,
                content=normalized[-1].content + "\n\n" + msg.content
            )
        else:
            # 不同角色，直接添加
            normalized.append(msg)
            last_role = msg.role

    # 更新消息列表
    if len(normalized) != original_len:
        loop.messages = normalized
        loop._trim_history(max_messages=30)

        if _ev:
            _ev(
                "messages_normalized",
                {
                    "stage": stage,
                    "step_id": step_id,
                    "before": original_len,
                    "after": len(loop.messages),
                    "merged_count": original_len - len(loop.messages),
                }
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
    # 记录本次 stage/step_id，供后续 request/response 日志使用（避免把历史轮次 messages 打出来）
    try:
        loop._last_llm_stage = stage
        loop._last_llm_step_id = step_id
    except Exception:
        pass

    # 0) 估算 prompt tokens（轻量，不依赖服务端 usage）
    prompt_tokens_est = 0
    try:
        prompt_tokens_est = sum(estimate_tokens(m.content) for m in (loop.messages or []))
    except Exception as ex:
        # P1-1: 异常写入 file-only 日志，便于排查
        loop.file_only_logger.warning(f"估算 prompt tokens 失败: {ex}", exc_info=True)
        prompt_tokens_est = 0

    # 1) 记录/打印请求参数（model 等）与请求数据摘要
    try:
        # 构建完整的 messages 列表（用于 TUI 显示系统/用户提示词）
        messages_full = [
            {"role": msg.role, "content": msg.content}
            for msg in loop.messages
        ]
        req_obj = {
            "stage": stage,
            "step_id": step_id,
            "base_url": loop.llm.base_url,
            "api_mode": loop.llm.api_mode,
            "model": loop.llm.model or "auto",
            "temperature": loop.llm.temperature,
            "max_tokens": loop.llm.max_tokens,
            # 估算 prompt tokens（用于 enhanced UI 实时显示 Context；不依赖服务端 usage）
            "prompt_tokens_est": prompt_tokens_est,
            "messages_count": len(loop.messages),
            "last_role": loop.messages[-1].role if loop.messages else None,
            "last_content_preview": (loop.messages[-1].content) if (loop.messages and len(loop.messages[-1].content) > 200) else (loop.messages[-1].content if loop.messages else None),
            # 完整 messages 列表（供 TUI 显示系统/用户提示词）
            "messages": messages_full,
        }
        # 写入文件（详细）：只打印本次请求新增的 user，不打印历史轮次 messages
        log_llm_request_params_to_file(loop)
        # 控制台/trace（摘要）
        if _ev:
            _ev("llm_request_params", req_obj)
        loop.logger.info(f"[dim]LLM 请求参数: model={req_obj['model']} api_mode={req_obj['api_mode']} messages={req_obj['messages_count']}[/dim]")
    except Exception as ex:
        # P1-1: 打印失败不影响主流程，但写入 file-only 日志便于排查
        loop.file_only_logger.warning(f"LLM 请求参数记录失败: {ex}", exc_info=True)

    # 2) 发起请求
    t0 = time.time()
    assistant_text = loop.llm.chat(loop.messages)
    elapsed_ms = int((time.time() - t0) * 1000)

    # 3) 记录/打印返回数据摘要（不依赖 tool_call，tool_call 在上层解析后另行落盘）
    try:
        resp_obj = {
            "stage": stage,
            "step_id": step_id,
            "text_length": len(assistant_text),
            "text_preview": assistant_text,
        }
        # 返回日志：只打印本次返回 assistant_text（不打印历史轮次）
        log_llm_response_data_to_file(loop, assistant_text, tool_call=None)
        if _ev:
            _ev("llm_response_data", resp_obj)
        loop.logger.info(f"[dim]LLM 返回摘要: text_length={resp_obj['text_length']}[/dim]")
    except Exception as ex:
        loop.file_only_logger.warning(f"LLM 响应后处理异常: {ex}", exc_info=True)

    # 4) 记录用量（会话级）
    try:
        completion_tokens_est = estimate_tokens(assistant_text)
        if hasattr(loop, "usage"):
            loop.usage.record_llm(
                prompt_tokens_est=prompt_tokens_est,
                completion_tokens_est=completion_tokens_est,
                elapsed_ms=elapsed_ms,
            )
        if _ev:
            _ev(
                "llm_usage",
                {
                    "stage": stage,
                    "step_id": step_id,
                    "elapsed_ms": elapsed_ms,
                    "prompt_tokens_est": prompt_tokens_est,
                    "completion_tokens_est": completion_tokens_est,
                    "total_tokens_est": prompt_tokens_est + completion_tokens_est,
                    "totals": (loop.usage.summary() if hasattr(loop, "usage") else None),
                },
            )
    except Exception as ex:
        # P1-1: 用量统计失败不影响主流程，但写入 file-only 日志便于排查
        loop.file_only_logger.warning(f"LLM 用量统计失败: {ex}", exc_info=True)

    return assistant_text


def log_llm_request_params_to_file(loop: "AgentLoop") -> None:
    """
    纯文本：只打印"本次请求的最后一条 user 文本"。
    
    修复：不再依赖 _llm_log_cursor（因为 normalize_messages_for_llama 会合并消息导致 cursor 失效）。
    业界做法：直接找 messages 中最后一条 user 消息。
    """
    llm_cfg = getattr(getattr(loop, "cfg", None), "llm_detail_logging", None)
    enabled = bool(getattr(llm_cfg, "enabled", True)) if llm_cfg is not None else True
    log_to_file = bool(getattr(llm_cfg, "log_to_file", True)) if llm_cfg is not None else True
    log_to_console = bool(getattr(llm_cfg, "log_to_console", False)) if llm_cfg is not None else False
    include_params = bool(getattr(llm_cfg, "include_params", True)) if llm_cfg is not None else True
    include_caller = bool(getattr(llm_cfg, "include_caller", False)) if llm_cfg is not None else False
    max_user_chars = int(getattr(llm_cfg, "max_user_chars", 20000) or 0) if llm_cfg is not None else 0

    if not enabled:
        return

    # 修复：不再使用 cursor，直接找最后一条 user 消息
    # 这样即使 normalize_messages_for_llama 合并了消息，也能正确打印
    new_users: list[ChatMessage] = []
    for msg in reversed(loop.messages or []):
        if getattr(msg, "role", None) == "user":
            new_users.insert(0, msg)
            break  # 只取最后一条 user 消息（本轮输入）
        elif getattr(msg, "role", None) == "assistant":
            # 遇到 assistant 就停止，说明之前的 user 是历史轮次的
            break

    caller = None
    if include_caller:
        # 轻量取外层调用点：跳过 llm_io 自身帧
        frame = None
        try:
            frame = inspect.currentframe()
            cur = frame.f_back if frame else None
            while cur is not None:
                fn = cur.f_code.co_filename or ""
                mod = cur.f_globals.get("__name__", "") or ""
                func = cur.f_code.co_name or "<unknown>"
                if not fn.endswith("llm_io.py"):
                    caller = f"{mod}.{func} ({fn}:{getattr(cur, 'f_lineno', 0)})"
                    break
                cur = cur.f_back
        except Exception:
            caller = None
        finally:
            try:
                del frame
            except Exception:
                pass

    # 按模板输出纯文本块（符合你要求：不是 JSON，直接打印发送了什么）
    lines: list[str] = []
    if caller:
        lines.append(f"[caller] {caller}")
    lines.append("===== 本轮发送给 LLM 的新增 user 文本 =====")
    if include_params:
        try:
            lines.append(
                f"model={loop.llm.model} api_mode={loop.llm.api_mode} max_tokens={loop.llm.max_tokens} "
                f"temperature={loop.llm.temperature} base_url={loop.llm.base_url} "
                f"stage={getattr(loop, '_last_llm_stage', None)} step_id={getattr(loop, '_last_llm_step_id', None)}"
            )
        except Exception:
            pass

    for i, m in enumerate(new_users, start=1):
        content = m.content or ""
        out = content
        truncated = False
        if max_user_chars > 0 and len(out) > max_user_chars:
            out = out[:max_user_chars]
            truncated = True
        lines.append(f"--- user[{i}] ---")
        if truncated:
            lines.append(f"[truncated] original_len={len(content)} max_user_chars={max_user_chars}")
        lines.append(out)

    text = "\n".join(lines)
    if log_to_file:
        loop.file_only_logger.info(text)
    if log_to_console:
        loop.logger.info(text)


def log_llm_response_data_to_file(loop: "AgentLoop", assistant_text: str, tool_call: dict[str, Any] | None) -> None:
    """纯文本：只打印“本次返回 assistant_text”，不打印历史轮次 messages。"""
    llm_cfg = getattr(getattr(loop, "cfg", None), "llm_detail_logging", None)
    enabled = bool(getattr(llm_cfg, "enabled", True)) if llm_cfg is not None else True
    log_to_file = bool(getattr(llm_cfg, "log_to_file", True)) if llm_cfg is not None else True
    log_to_console = bool(getattr(llm_cfg, "log_to_console", False)) if llm_cfg is not None else False
    include_tool_call = bool(getattr(llm_cfg, "include_tool_call", True)) if llm_cfg is not None else True
    max_response_chars = int(getattr(llm_cfg, "max_response_chars", 20000) or 0) if llm_cfg is not None else 0

    if not enabled:
        return

    out = assistant_text or ""
    truncated = False
    if max_response_chars > 0 and len(out) > max_response_chars:
        out = out[:max_response_chars]
        truncated = True

    lines: list[str] = []
    lines.append("===== 本轮 LLM 返回文本 =====")
    lines.append("--- assistant_text ---")
    if truncated:
        lines.append(f"[truncated] original_len={len(assistant_text or '')} max_response_chars={max_response_chars}")
    lines.append(out)
    if include_tool_call and tool_call is not None:
        lines.append("--- tool_call (parsed) ---")
        try:
            lines.append(json.dumps(tool_call, ensure_ascii=False, indent=2))
        except Exception:
            lines.append("<unserializable>")
    text = "\n".join(lines)
    if log_to_file:
        loop.file_only_logger.info(text)
    if log_to_console:
        loop.logger.info(text)


