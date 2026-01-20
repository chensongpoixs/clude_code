import json
from pathlib import Path
from typing import Any, Callable, TYPE_CHECKING

from clude_code.policy.command_policy import evaluate_command
from clude_code.tooling.local_tools import ToolResult
from .tool_dispatch import TOOL_REGISTRY

if TYPE_CHECKING:
    from .agent_loop import AgentLoop

    """
    统一工具执行生命周期：策略检查 -> 确认 -> 审计 -> 执行 -> 验证。

    大文件治理说明：
    - 这段逻辑会被 Planning 与 ReAct 两种模式复用，单独抽离后更易维护/测试。
    """
def run_tool_lifecycle(
    loop: "AgentLoop",
    name: str,
    args: dict[str, Any],
    trace_id: str,
    confirm: Callable[[str], bool],
    _ev: Callable[[str, dict[str, Any]], None],
) -> ToolResult:

    spec = TOOL_REGISTRY.get(name)
    side_effects = spec.side_effects if spec is not None else set()

    # 0) 工具权限（对标 Claude Code：allowedTools/disallowedTools）
    allowed = list(getattr(loop.cfg.policy, "allowed_tools", []) or [])
    denied = set(getattr(loop.cfg.policy, "disallowed_tools", []) or [])
    if allowed and name not in allowed:
        loop.logger.warning(f"[red]✗ 工具被 allowed_tools 限制拒绝: {name}[/red]")
        loop.audit.write(trace_id=trace_id, event="policy_deny_tool", data={"tool": name, "reason": "not_in_allowed_tools"})
        _ev("policy_deny_tool", {"tool": name, "reason": "not_in_allowed_tools"})
        return ToolResult(ok=False, error={"code": "E_POLICY", "message": f"tool not allowed: {name}"})
    if name in denied:
        loop.logger.warning(f"[red]✗ 工具被 disallowed_tools 禁止: {name}[/red]")
        loop.audit.write(trace_id=trace_id, event="policy_deny_tool", data={"tool": name, "reason": "in_disallowed_tools"})
        _ev("policy_deny_tool", {"tool": name, "reason": "in_disallowed_tools"})
        return ToolResult(ok=False, error={"code": "E_POLICY", "message": f"tool disallowed: {name}"})

    # 1. 确认策略 (MVP: 写/执行 确认)
    if ("write" in side_effects) and loop.cfg.policy.confirm_write:
        loop.logger.info(f"[yellow]⚠ 需要用户确认写文件操作: {name}[/yellow]")
        if not confirm(f"确认写文件？tool={name} args={args}"):
            loop.logger.warning(f"[red]✗ 用户拒绝写文件操作: {name}[/red]")
            loop.audit.write(trace_id=trace_id, event="confirm_deny", data={"tool": name, "args": args})
            _ev("denied_by_user", {"tool": name})
            return ToolResult(ok=False, error={"code": "E_DENIED", "message": "User denied write access"})
        loop.logger.info(f"[green]✓ 用户确认写文件操作: {name}[/green]")

    if "exec" in side_effects:
        cmd_key = (spec.exec_command_key if spec is not None else None) or "command"
        cmd = str(args.get(cmd_key, ""))
        if not cmd.strip():
            return ToolResult(ok=False, error={"code": "E_INVALID_ARGS", "message": f"missing arg: {cmd_key}"})
        # 内部安全评估（黑名单）
        decision = evaluate_command(cmd, allow_network=loop.cfg.policy.allow_network)
        if not decision.ok:
            loop.logger.warning(f"[red]✗ 策略拒绝命令: {cmd} (原因: {decision.reason})[/red]")
            loop.audit.write(trace_id=trace_id, event="policy_deny_cmd", data={"command": cmd, "reason": decision.reason})
            _ev("policy_deny_cmd", {"command": cmd, "reason": decision.reason})
            return ToolResult(ok=False, error={"code": "E_POLICY", "message": decision.reason})
        # 用户交互确认
        if ("exec" in side_effects) and loop.cfg.policy.confirm_exec:
            loop.logger.info(f"[yellow]⚠ 需要用户确认执行命令: {cmd}[/yellow]")
            if not confirm(f"确认执行命令？{cmd}"):
                loop.logger.warning(f"[red]✗ 用户拒绝执行命令: {cmd}[/red]")
                loop.audit.write(trace_id=trace_id, event="confirm_deny", data={"tool": name, "command": cmd})
                _ev("denied_by_user", {"tool": name})
                return ToolResult(ok=False, error={"code": "E_DENIED", "message": "User denied command execution"})
            loop.logger.info("[green]✓ 用户确认执行命令[/green]")

    # 2. 核心执行
    loop.logger.info(f"[bold cyan]▶ 执行工具: {name}[/bold cyan]")
    result = loop._dispatch_tool(name, args)

    # --- 阶段 C: 记录修改过的路径 ---
    if result.ok and (name in {"write_file", "apply_patch", "undo_patch"}):
        path_str = args.get("path")
        if path_str:
            from clude_code.tooling.workspace import resolve_in_workspace
            abs_path = resolve_in_workspace(Path(loop.cfg.workspace_root), path_str)
            loop._turn_modified_paths.add(abs_path)

    # 详细日志输出
    result_summary = loop._format_result_summary(name, result)
    if result.ok:
        loop.logger.info(f"[green]✓ 工具执行成功: {name}[/green] [结果] {result_summary}")
    else:
        error_msg = result.error.get("message", str(result.error)) if isinstance(result.error, dict) else str(result.error)
        loop.logger.error(f"[red]✗ 工具执行失败: {name}[/red] [错误] {error_msg} [结果] {result_summary}")

    # 3. 记录审计
    audit_data: dict[str, Any] = {"tool": name, "args": args, "ok": result.ok, "error": result.error}
    if name in {"apply_patch", "undo_patch"} and result.ok and result.payload:
        audit_data["payload"] = result.payload  # 记录 hash/undo_id
    loop.audit.write(trace_id=trace_id, event="tool_call", data=audit_data)

    # 3.1 记录用量（工具调用）
    try:
        if hasattr(loop, "usage"):
            loop.usage.record_tool(name=name, ok=bool(result.ok))
        _ev("tool_usage", {"tool": name, "ok": bool(result.ok), "totals": (loop.usage.summary() if hasattr(loop, "usage") else None)})
    except Exception as ex:
        # P1-1: 用量统计失败不影响主流程，但写入 file-only 日志便于排查
        loop.file_only_logger.warning(f"工具用量统计失败: {ex}", exc_info=True)

    # 4. 记录详细结果到文件
    loop.file_only_logger.info(
        f"工具执行结果 [tool={name}] [ok={result.ok}] "
        f"[error={json.dumps(result.error, ensure_ascii=False) if result.error else None}] "
        f"[payload_keys={(result.payload.keys()) if result.payload else []}]"
    )

    # 5. 自动化验证闭环 (自愈)
    if result.ok and (("write" in side_effects) or ("exec" in side_effects)):
        loop.logger.info("[bold magenta]🔍 自动触发验证闭环 (选择性测试)...[/bold magenta]")
        # 传递本轮已修改的文件列表
        v_res = loop.verifier.run_verify(modified_paths=list(loop._turn_modified_paths))
        _ev("autofix_check", {"ok": v_res.ok, "type": v_res.type, "summary": v_res.summary})

        if v_res.ok:
            loop.logger.info(f"[green]✓ 验证通过[/green] [摘要] {v_res.summary}")
        else:
            error_details = "; ".join([f"{err.file}:{err.line} {err.message}" for err in (v_res.errors or [])[:3]])
            loop.logger.warning(f"[yellow]⚠ 验证失败[/yellow] [摘要] {v_res.summary} [错误] {error_details}")
            loop.file_only_logger.warning(
                f"验证失败详情 [tool={name}] [errors={json.dumps([{'file': err.file, 'line': err.line, 'message': err.message} for err in (v_res.errors or [])], ensure_ascii=False)}]"
            )
            v_msg = f"\n\n[验证失败 - 自动自检结果]\n状态: {v_res.summary}\n"
            if v_res.errors:
                v_msg += "具体错误:\n"
                for err in v_res.errors[:3]:
                    v_msg += f"- {err.file}:{err.line} {err.message}\n"
            if result.payload is None:
                result = ToolResult(ok=True, payload={"verification_error": v_msg})
            else:
                result.payload["verification_error"] = v_msg

    return result


