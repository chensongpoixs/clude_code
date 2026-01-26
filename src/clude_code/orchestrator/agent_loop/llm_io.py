from __future__ import annotations

import hashlib
import json
import inspect
import time
from typing import Any, Callable, TYPE_CHECKING

from clude_code.llm.http_client import ChatMessage
from clude_code.observability.usage import estimate_tokens

if TYPE_CHECKING:
    from .agent_loop import AgentLoop


def _ensure_strict_alternation(loop: "AgentLoop") -> None:
    """
    在发送请求前，确保消息角色严格交替（最后一道防线）。
    
    Gemma 模型要求：system 后必须是 user，之后严格 user/assistant/user/assistant/...
    """
    if not loop.messages or len(loop.messages) < 2:
        return
    
    # 分离 system 消息
    system_msg = loop.messages[0] if loop.messages[0].role == "system" else None
    start_idx = 1 if system_msg else 0
    
    # 重建严格交替的消息列表
    strict_msgs: list[ChatMessage] = []
    if system_msg:
        strict_msgs.append(system_msg)
    
    expected_role = "user"  # system 后第一条必须是 user
    
    for msg in loop.messages[start_idx:]:
        if msg.role == expected_role:
            # 角色正确
            strict_msgs.append(msg)
            expected_role = "assistant" if expected_role == "user" else "user"
        elif msg.role == "user" and expected_role == "assistant":
            # 连续 user，插入占位 assistant
            strict_msgs.append(ChatMessage(role="assistant", content="好的。"))
            strict_msgs.append(msg)
            expected_role = "assistant"
        elif msg.role == "assistant" and expected_role == "user":
            # 连续 assistant 或第一条是 assistant，插入占位 user
            strict_msgs.append(ChatMessage(role="user", content="请继续。"))
            strict_msgs.append(msg)
            expected_role = "user"
        else:
            # 连续相同角色，合并
            if strict_msgs and strict_msgs[-1].role == msg.role:
                content = strict_msgs[-1].content
                if isinstance(content, str) and isinstance(msg.content, str):
                    strict_msgs[-1] = ChatMessage(role=msg.role, content=content + "\n\n" + msg.content)
    
    if len(strict_msgs) != len(loop.messages):
        loop.file_only_logger.debug(f"[FINAL_CHECK] 消息数调整: {len(loop.messages)} -> {len(strict_msgs)}")
    
    loop.messages = strict_msgs


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

    def _merge_message_content(existing_content, new_content):
        """
        合并消息内容，支持字符串和多模态内容。
        """
        if isinstance(existing_content, str) and isinstance(new_content, str):
            # 两个都是字符串
            return existing_content + "\n\n" + new_content
        elif isinstance(existing_content, list) and isinstance(new_content, str):
            # existing 是多模态，new 是字符串 - 追加文本
            # 找到最后一个文本部分，或者添加新文本部分
            merged = existing_content.copy()
            if merged and isinstance(merged[-1], dict) and merged[-1].get("type") == "text":
                # 合并到最后一个文本部分
                merged[-1]["text"] += "\n\n" + new_content
            else:
                # 添加新的文本部分
                merged.append({"type": "text", "text": new_content})
            return merged
        elif isinstance(existing_content, str) and isinstance(new_content, list):
            # existing 是字符串，new 是多模态 - 转换为多模态格式
            merged = [{"type": "text", "text": existing_content}]
            merged.extend(new_content)
            return merged
        elif isinstance(existing_content, list) and isinstance(new_content, list):
            # 两个都是多模态 - 合并
            merged = existing_content.copy()
            merged.extend(new_content)
            return merged
        else:
            # 其他情况，直接使用新内容
            return new_content

    for msg in filtered:
        if not normalized:
            # 第一条消息直接添加
            normalized.append(msg)
            last_role = msg.role
        elif msg.role == last_role:
            # 连续相同角色，合并内容
            merged_content = _merge_message_content(normalized[-1].content, msg.content)
            normalized[-1] = ChatMessage(
                role=msg.role,  # 使用当前消息的角色，确保类型正确
                content=merged_content
            )
        else:
            # 不同角色，直接添加
            normalized.append(msg)
            last_role = msg.role

    # 第三遍：确保严格交替 user/assistant/user/assistant/...（Gemma 等模型的 chat template 要求）
    # Gemma chat template 检查: (message['role'] == 'user') != (loop.index0 % 2 == 0)
    # 即：偶数索引(0,2,4...)必须是 user，奇数索引(1,3,5...)必须是 assistant
    final_normalized: list[ChatMessage] = []
    
    # 分离 system 消息
    system_msg = None
    non_system_msgs = []
    for msg in normalized:
        if msg.role == "system":
            system_msg = msg
        else:
            non_system_msgs.append(msg)
    
    # [DEBUG] 打印分离后的角色序列
    loop.file_only_logger.debug(f"[NORMALIZE] 分离后非 system 消息角色: {[m.role for m in non_system_msgs]}")
    
    # 确保非 system 消息严格交替
    strict_alternating: list[ChatMessage] = []
    expected_role = "user"  # 第一条非 system 消息必须是 user
    
    for msg in non_system_msgs:
        if msg.role == expected_role:
            # 角色正确，直接添加
            strict_alternating.append(msg)
            expected_role = "assistant" if expected_role == "user" else "user"
        elif msg.role == "user" and expected_role == "assistant":
            # 期望 assistant 但收到 user，插入占位 assistant 后添加
            placeholder = ChatMessage(role="assistant", content="好的，继续。")
            strict_alternating.append(placeholder)
            strict_alternating.append(msg)
            expected_role = "assistant"  # 添加了 assistant + user，下一个期望 assistant
        elif msg.role == "assistant" and expected_role == "user":
            # 期望 user 但收到 assistant，插入占位 user 后添加
            placeholder = ChatMessage(role="user", content="请继续。")
            strict_alternating.append(placeholder)
            strict_alternating.append(msg)
            expected_role = "user"  # 添加了 user + assistant，下一个期望 user
        else:
            # 连续相同角色，合并到上一条
            if strict_alternating and strict_alternating[-1].role == msg.role:
                merged_content = _merge_message_content(strict_alternating[-1].content, msg.content)
                strict_alternating[-1] = ChatMessage(role=msg.role, content=merged_content)
    
    # 组装最终结果：system（如有）+ 严格交替的消息
    if system_msg:
        final_normalized.append(system_msg)
    final_normalized.extend(strict_alternating)
    
    # [DEBUG] 打印规范化后的角色序列
    loop.file_only_logger.debug(f"[NORMALIZE] 规范化后角色: {[m.role for m in final_normalized]}")
    
    normalized = final_normalized

    # 总是更新消息列表（确保规范化结果生效）
    loop.messages = normalized
    loop._trim_history(max_messages=30)

    if _ev and len(normalized) != original_len:
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
    - 统一出口处打印/落盘"请求参数 + 请求数据摘要 + 返回数据摘要"，便于复盘 400/500/超时问题。
    - 避免在多个调用点各自打印造成遗漏或输出不一致。
    """
    normalize_messages_for_llama(loop, stage, step_id=step_id, _ev=_ev)
    # 记录本次 stage/step_id，供后续 request/response 日志使用（避免把历史轮次 messages 打出来）
    try:
        loop._last_llm_stage = stage
        loop._last_llm_step_id = step_id
    except Exception:
        pass
    
    # 提前记录 provider 信息（用于日志输出正确的当前 provider，避免拿到上一次的）
    try:
        from clude_code.llm import get_model_manager
        mm = get_model_manager()
        current_provider = mm.get_provider()
        if current_provider:
            loop._last_provider_id = mm.get_current_provider_id()
            loop._last_provider_base_url = getattr(current_provider, "config", None) and getattr(current_provider.config, "base_url", "") or ""
            loop._last_provider_model = current_provider.current_model
        else:
            loop._last_provider_id = ""
            loop._last_provider_base_url = ""
            loop._last_provider_model = ""
    except Exception:
        loop._last_provider_id = ""
        loop._last_provider_base_url = ""
        loop._last_provider_model = ""

    # 0) 估算 prompt tokens（轻量，不依赖服务端 usage）
    prompt_tokens_est = 0
    try:
        prompt_tokens_est = sum(estimate_tokens(str(m.content)) for m in (loop.messages or []))
    except Exception as ex:
        # P1-1: 异常写入 file-only 日志，便于排查
        loop.file_only_logger.warning(f"估算 prompt tokens 失败: {ex}", exc_info=True)
        prompt_tokens_est = 0

    # P0 紧急截断：如果 token 使用率 > 95%，强制裁剪到只保留 system + 最近 4 条消息
    # 注意：保留偶数条非 system 消息（4 条），确保截断后仍可能满足 user/assistant 交替
    max_tokens = getattr(loop.llm, "max_tokens", 32768) or 32768
    utilization = prompt_tokens_est / max_tokens if max_tokens > 0 else 0
    if utilization > 0.95 and len(loop.messages) > 5:
        loop.logger.warning(
            f"[red]⚠ 紧急截断触发: {prompt_tokens_est} tokens ({utilization*100:.1f}%) > 95% 预算[/red]"
        )
        # 保留 system + 最近 4 条消息（偶数条，确保交替）
        system_msg = loop.messages[0] if loop.messages and loop.messages[0].role == "system" else None
        recent_msgs = loop.messages[-4:]
        if system_msg:
            loop.messages = [system_msg] + recent_msgs
        else:
            loop.messages = recent_msgs
        # 截断后重新规范化，确保消息角色严格交替
        normalize_messages_for_llama(loop, stage, step_id=step_id, _ev=_ev)
        # 重新估算
        prompt_tokens_est = sum(estimate_tokens(str(m.content)) for m in (loop.messages or []))
        loop.logger.warning(f"[yellow]紧急截断后: {len(loop.messages)} 条消息, {prompt_tokens_est} tokens[/yellow]")

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

    # 2) 发起请求前最终确保消息角色交替（防止 _trim_history 破坏规范化结果）
    _ensure_strict_alternation(loop)
    
    # 3) 发起请求（优先走多厂商 Provider；未注册时回退 loop.llm）
    t0 = time.time()
    assistant_text: str
    used_provider_id: str | None = None
    used_provider_base_url: str | None = None
    used_provider_model: str | None = None
    try:
        # ModelManager 是全局单例；Slash Commands 也会对其进行切换
        from clude_code.llm import get_model_manager

        mm = get_model_manager()
        provider = mm.get_provider()
        if provider is not None:
            used_provider_id = mm.get_current_provider_id() or getattr(provider, "PROVIDER_ID", None)
            used_provider_base_url = getattr(getattr(provider, "config", None), "base_url", "") or None
            used_provider_model = provider.current_model or None

            # 重要：model=None 时由 provider 自行选择（通常为 current_model 或 default_model）
            assistant_text = provider.chat(
                loop.messages,
                model=used_provider_model,
                temperature=getattr(loop.llm, "temperature", 0.2),
                max_tokens=getattr(loop.llm, "max_tokens", 4096),
            )
        else:
            assistant_text = loop.llm.chat(loop.messages)
    except Exception as e:
        # 记录异常便于排查，然后回退 loop.llm（避免 provider 注册/配置问题导致整体不可用）
        loop.file_only_logger.warning(f"Provider 调用失败，回退到 loop.llm: {e}", exc_info=True)
        assistant_text = loop.llm.chat(loop.messages)

    elapsed_ms = int((time.time() - t0) * 1000)

    # 把“本次实际使用的 provider 信息”挂到 loop 上，供日志打印（不改动 loop.llm 本身）
    try:
        loop._active_provider_id = used_provider_id
        loop._active_provider_base_url = used_provider_base_url
        loop._active_provider_model = used_provider_model
    except Exception:
        pass

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
    
    # 输出系统提示词摘要（只在内容变化时输出，避免日志噪音）
    include_system_prompt = bool(getattr(llm_cfg, "include_system_prompt", True)) if llm_cfg is not None else True
    max_system_chars = int(getattr(llm_cfg, "max_system_chars", 2000) or 2000) if llm_cfg is not None else 2000
    if include_system_prompt and loop.messages:
        system_msg = next((m for m in loop.messages if m.role == "system"), None)
        if system_msg and system_msg.content:
            sys_content = system_msg.content
            sys_len = len(sys_content)
            
            # 计算哈希，检测是否变化
            sys_hash = hashlib.md5(sys_content.encode("utf-8", errors="replace")).hexdigest()[:16]
            last_hash = getattr(loop, "_last_logged_system_prompt_hash", None)
            
            if sys_hash != last_hash:
                # 系统提示词有变化，输出摘要
                loop._last_logged_system_prompt_hash = sys_hash
                lines.append("===== System Prompt 摘要（有变化）=====")
                lines.append(f"[系统提示词长度: {sys_len} chars, hash: {sys_hash}]")
                if sys_len > max_system_chars:
                    # 截断显示：头部 + 尾部
                    head = sys_content[:max_system_chars // 2]
                    tail = sys_content[-(max_system_chars // 2):]
                    lines.append(f"{head}\n...[省略 {sys_len - max_system_chars} chars]...\n{tail}")
                else:
                    lines.append(sys_content)
            # 如果没变化，不输出系统提示词内容
    
    lines.append("===== 本轮发送给 LLM 的新增 user 文本 =====")
    if include_params:
        try:
            # provider 元信息（使用 _last_provider_* 因为它是在 LLM 调用前设置的）
            pid = getattr(loop, "_last_provider_id", None)
            purl = getattr(loop, "_last_provider_base_url", None)
            pmodel = getattr(loop, "_last_provider_model", None)
            if pid or purl or pmodel:
                lines.append(
                    f"provider_id={pid} provider_base_url={purl} provider_model={pmodel}"
                )
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


