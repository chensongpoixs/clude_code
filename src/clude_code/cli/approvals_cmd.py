from __future__ import annotations

import typer

from clude_code.core.project_paths import DEFAULT_PROJECT_ID
from clude_code.orchestrator.approvals import ApprovalStore

app = typer.Typer(help="审批流（Phase2）：列出/批准/拒绝审批单")


@app.command("list")
def list_approvals(
    project_id: str = typer.Option(DEFAULT_PROJECT_ID, "--project-id", "-P", help="项目 ID"),
    workspace_root: str = typer.Option(".", "--workspace-root", help="工作区根目录（默认 .）"),
    status: str = typer.Option("pending", "--status", help="pending|approved|rejected"),
    limit: int = typer.Option(20, "--limit", help="最多返回条数"),
) -> None:
    store = ApprovalStore(workspace_root=workspace_root, project_id=(project_id or DEFAULT_PROJECT_ID))
    items = store.list(status=(status if status in {"pending", "approved", "rejected"} else "pending"), limit=limit)
    if not items:
        typer.echo("NO_APPROVALS")
        return
    for it in items:
        typer.echo(f"{it.id}\t{it.status}\t{it.risk_level}\tintent={it.intent_name}\ttrace={it.trace_id}")


@app.command("approve")
def approve(
    approval_id: str = typer.Argument(..., help="审批单 ID（apr_xxx）"),
    project_id: str = typer.Option(DEFAULT_PROJECT_ID, "--project-id", "-P", help="项目 ID"),
    workspace_root: str = typer.Option(".", "--workspace-root", help="工作区根目录（默认 .）"),
    by: str = typer.Option("cli", "--by", help="审批人标识"),
    comment: str = typer.Option("", "--comment", help="备注"),
) -> None:
    store = ApprovalStore(workspace_root=workspace_root, project_id=(project_id or DEFAULT_PROJECT_ID))
    req = store.approve(approval_id, decided_by=by, comment=comment)
    if not req:
        raise typer.BadParameter(f"未找到审批单: {approval_id}")
    typer.echo(f"OK: approved {req.id}")


@app.command("reject")
def reject(
    approval_id: str = typer.Argument(..., help="审批单 ID（apr_xxx）"),
    project_id: str = typer.Option(DEFAULT_PROJECT_ID, "--project-id", "-P", help="项目 ID"),
    workspace_root: str = typer.Option(".", "--workspace-root", help="工作区根目录（默认 .）"),
    by: str = typer.Option("cli", "--by", help="审批人标识"),
    comment: str = typer.Option("", "--comment", help="备注"),
) -> None:
    store = ApprovalStore(workspace_root=workspace_root, project_id=(project_id or DEFAULT_PROJECT_ID))
    req = store.reject(approval_id, decided_by=by, comment=comment)
    if not req:
        raise typer.BadParameter(f"未找到审批单: {approval_id}")
    typer.echo(f"OK: rejected {req.id}")


@app.command("run")
def run(
    approval_id: str = typer.Argument(..., help="审批单 ID（apr_xxx）"),
    project_id: str = typer.Option(DEFAULT_PROJECT_ID, "--project-id", "-P", help="项目 ID"),
    workspace_root: str = typer.Option(".", "--workspace-root", help="工作区根目录（默认 .）"),
    yes: bool = typer.Option(False, "--yes", help="自动同意需要确认的操作（有风险）"),
) -> None:
    """
    批准后继续执行：加载审批单内的 plan 快照并直接进入执行阶段（跳过 planning）。
    """
    from clude_code.config.config import CludeConfig
    from clude_code.orchestrator.planner import Plan
    from clude_code.orchestrator.agent_loop.agent_loop import AgentLoop
    from clude_code.orchestrator.state_m import AgentState
    from clude_code.orchestrator.agent_loop.agent_loop import _try_parse_tool_call as _parse_tool_call
    from clude_code.orchestrator.agent_loop.agent_loop import _tool_result_to_message as _tool_result_to_message

    pid = (project_id or DEFAULT_PROJECT_ID).strip() or DEFAULT_PROJECT_ID
    store = ApprovalStore(workspace_root=workspace_root, project_id=pid)
    req = store.get(approval_id)
    if not req:
        raise typer.BadParameter(f"未找到审批单: {approval_id}")
    if req.status != "approved":
        raise typer.BadParameter(f"审批单未批准，无法执行: id={req.id} status={req.status}")
    if not req.plan or not isinstance(req.plan, dict):
        raise typer.BadParameter(f"审批单缺少 plan 快照，无法执行: id={req.id}")

    plan = Plan.model_validate(req.plan)
    cfg = CludeConfig()
    loop = AgentLoop(cfg, project_id=pid)

    # confirm：CLI 版（支持 --yes）
    def _confirm(msg: str) -> bool:
        if yes:
            return True
        return typer.confirm(msg, default=False)

    events: list[dict[str, object]] = []
    trace_id = req.trace_id or loop.trace.session_id

    def _on_event(ev: dict[str, object]) -> None:
        events.append(ev)

    def _ev(name: str, data: dict[str, object]) -> None:
        _on_event({"event": name, "data": data})

    # 直接执行计划
    current_state = AgentState.EXECUTING

    def _set_state(st: AgentState, info: dict[str, object] | None = None) -> None:
        nonlocal current_state
        current_state = st
        payload: dict[str, object] = {"state": st.value}
        if info:
            payload.update(info)
        _ev("state", payload)

    llm_chat = (lambda stage, step_id=None: loop._llm_chat(stage, step_id=step_id, _ev=_ev))

    plan, tool_used, did_modify_code = loop._execute_plan_steps(
        plan,
        trace_id,
        set(),
        _confirm,
        events,
        _ev,
        llm_chat,
        _parse_tool_call,
        _tool_result_to_message,
        _set_state,
    )

    if plan is None:
        typer.echo("EXECUTION_STOPPED")
        raise typer.Exit(code=2)

    final = loop._execute_final_verification(plan, did_modify_code, trace_id, tool_used, _ev, _set_state)
    if final is not None:
        typer.echo(final.assistant_text)
        return
    typer.echo(f"OK: plan executed: {plan.title}")


