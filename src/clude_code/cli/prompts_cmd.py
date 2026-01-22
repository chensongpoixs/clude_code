from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer

from clude_code.core.project_paths import ProjectPaths, DEFAULT_PROJECT_ID

app = typer.Typer(help="Prompt 运维命令：查看/切换/回滚 prompt 版本（写入 prompt_versions.json）")

def _prompts_root() -> Path:
    # src/clude_code/prompts/
    return (Path(__file__).resolve().parents[1] / "prompts").resolve()


def _versions_file(workspace_root: str, project_id: str, *, scope: str) -> Path:
    paths = ProjectPaths(workspace_root, project_id)
    return paths.prompt_versions_file(scope=scope)


def _read_versions(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"prompts": {}}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(obj, dict):
            return {"prompts": {}}
        if "prompts" not in obj or not isinstance(obj.get("prompts"), dict):
            obj["prompts"] = {}
        return obj
    except Exception:
        return {"prompts": {}}


def _write_versions(path: Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

def _resolve_versioned_ref(ref: str, version: str) -> str:
    p = Path(ref)
    stem = p.stem
    suffix = "".join(p.suffixes) or ""
    if suffix:
        return str(p.with_name(f"{stem}_v{version}{suffix}"))
    return str(p.with_name(f"{stem}_v{version}.md"))


def _read_yaml_front_matter(path: Path) -> tuple[dict[str, Any], str, bool, str]:
    """
    返回: (meta, body, has_front_matter, error_message)
    """
    txt = path.read_text(encoding="utf-8", errors="replace")
    s = txt.lstrip("\ufeff")
    if not s.startswith("---"):
        return {}, txt, False, ""
    lines = s.splitlines(True)
    if not lines or lines[0].strip() != "---":
        return {}, txt, False, ""
    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break
    if end_idx is None:
        return {}, txt, True, "front matter 未闭合（缺少第二个 ---）"
    head = "".join(lines[1:end_idx])
    body = "".join(lines[end_idx + 1 :])
    try:
        import yaml  # type: ignore

        meta = yaml.safe_load(head) or {}
        if not isinstance(meta, dict):
            return {}, body, True, "front matter 解析结果不是 dict"
        return meta, body, True, ""
    except Exception as e:
        return {}, body, True, f"front matter YAML 解析失败: {type(e).__name__}: {e}"


def _validate_front_matter(meta: dict[str, Any], *, expected_version: str | None = None) -> list[str]:
    errs: list[str] = []
    title = meta.get("title")
    ver = meta.get("version")
    layer = meta.get("layer")
    if not title or not isinstance(title, str):
        errs.append("front matter 缺少 title 或类型非法")
    if not ver or not isinstance(ver, str):
        errs.append("front matter 缺少 version 或类型非法")
    if expected_version and isinstance(ver, str) and ver.strip() != expected_version:
        errs.append(f"front matter version={ver!r} 与期望版本 {expected_version!r} 不一致")
    if not layer or not isinstance(layer, str):
        errs.append("front matter 缺少 layer 或类型非法")
    elif layer not in {"base", "domain", "task"}:
        errs.append("front matter layer 必须为 base|domain|task")
    return errs


@app.command("show")
def show(
    ref: str = typer.Argument("", help="可选：只查看某个 prompt ref（例如 user/stage/planning.j2）"),
    workspace_root: str = typer.Option(".", "--workspace-root", help="工作区根目录（默认 .）"),
    project_id: str = typer.Option(DEFAULT_PROJECT_ID, "--project-id", "-P", help="项目 ID（用于路径计算；prompt_versions.json 在 registry 下全局共享）"),
    scope: str = typer.Option("global", "--scope", help="版本指针隔离策略：global|project（默认 global）"),
) -> None:
    """查看 prompt_versions.json 当前内容。"""
    pid = (project_id or "").strip() or DEFAULT_PROJECT_ID
    p = _versions_file(workspace_root, pid, scope=scope)
    obj = _read_versions(p)
    prompts = obj.get("prompts") or {}
    if ref:
        it = prompts.get(ref) or {}
        typer.echo(json.dumps({ref: it}, ensure_ascii=False, indent=2))
        return
    typer.echo(json.dumps(obj, ensure_ascii=False, indent=2))


@app.command("pin")
def pin(
    ref: str = typer.Argument(..., help="prompt ref（例如 user/stage/planning.j2）"),
    version: str = typer.Argument(..., help="新版本号（精确 SemVer，例如 1.0.1）"),
    workspace_root: str = typer.Option(".", "--workspace-root", help="工作区根目录（默认 .）"),
    project_id: str = typer.Option(DEFAULT_PROJECT_ID, "--project-id", "-P", help="项目 ID"),
    scope: str = typer.Option("global", "--scope", help="版本指针隔离策略：global|project（默认 global）"),
) -> None:
    """设置某个 prompt ref 的 current 版本，并自动记录 previous（用于回滚）。"""
    pid = (project_id or "").strip() or DEFAULT_PROJECT_ID
    p = _versions_file(workspace_root, pid, scope=scope)
    obj = _read_versions(p)
    prompts = obj.setdefault("prompts", {})
    it = prompts.get(ref) or {}
    cur = (it.get("current") or "").strip()
    if cur and cur != version:
        it["previous"] = cur
    it["current"] = version
    prompts[ref] = it
    _write_versions(p, obj)
    typer.echo(f"OK: pinned {ref} current={version} (previous={it.get('previous','')})")


@app.command("rollback")
def rollback(
    ref: str = typer.Argument(..., help="prompt ref（例如 user/stage/planning.j2）"),
    workspace_root: str = typer.Option(".", "--workspace-root", help="工作区根目录（默认 .）"),
    project_id: str = typer.Option(DEFAULT_PROJECT_ID, "--project-id", "-P", help="项目 ID"),
    scope: str = typer.Option("global", "--scope", help="版本指针隔离策略：global|project（默认 global）"),
) -> None:
    """回滚：把 current 置为 previous（若存在），并把原 current 写回 previous（形成可往返回滚）。"""
    pid = (project_id or "").strip() or DEFAULT_PROJECT_ID
    p = _versions_file(workspace_root, pid, scope=scope)
    obj = _read_versions(p)
    prompts = obj.setdefault("prompts", {})
    it = prompts.get(ref) or {}
    cur = (it.get("current") or "").strip()
    prev = (it.get("previous") or "").strip()
    if not prev:
        raise typer.BadParameter(f"{ref} 没有 previous，无法回滚")
    it["current"] = prev
    if cur and cur != prev:
        it["previous"] = cur
    prompts[ref] = it
    _write_versions(p, obj)
    typer.echo(f"OK: rollback {ref} current={it['current']} previous={it.get('previous','')}")


@app.command("unpin")
def unpin(
    ref: str = typer.Argument(..., help="prompt ref（例如 user/stage/planning.j2）"),
    workspace_root: str = typer.Option(".", "--workspace-root", help="工作区根目录（默认 .）"),
    project_id: str = typer.Option(DEFAULT_PROJECT_ID, "--project-id", "-P", help="项目 ID"),
    scope: str = typer.Option("global", "--scope", help="版本指针隔离策略：global|project（默认 global）"),
) -> None:
    """移除某个 ref 的版本指针（删除 current/previous）。"""
    pid = (project_id or "").strip() or DEFAULT_PROJECT_ID
    p = _versions_file(workspace_root, pid, scope=scope)
    obj = _read_versions(p)
    prompts = obj.setdefault("prompts", {})
    if ref in prompts:
        prompts.pop(ref, None)
        _write_versions(p, obj)
        typer.echo(f"OK: unpinned {ref}")
        return
    typer.echo(f"NOOP: {ref} not found")


@app.command("validate")
def validate(
    ref: str = typer.Argument("", help="可选：只校验某个 ref（例如 user/stage/planning.j2）"),
    workspace_root: str = typer.Option(".", "--workspace-root", help="工作区根目录（默认 .）"),
    project_id: str = typer.Option(DEFAULT_PROJECT_ID, "--project-id", "-P", help="项目 ID"),
    scope: str = typer.Option("global", "--scope", help="版本指针隔离策略：global|project（默认 global）"),
) -> None:
    """
    校验 prompts 引用是否可用：
    - ref 文件存在
    - 若存在版本指针/current/previous 或 intents.yaml 指定版本，则版本化文件存在
    - front matter 合规（title/version/layer），且 version 匹配（若指定）
    """
    pid = (project_id or "").strip() or DEFAULT_PROJECT_ID
    versions_path = _versions_file(workspace_root, pid, scope=scope)
    versions = _read_versions(versions_path)
    prompts_map = versions.get("prompts") or {}

    refs: set[str] = set()
    # 1) 来自 prompt_versions.json
    for k in prompts_map.keys():
        if isinstance(k, str) and k.strip():
            refs.add(k.strip())

    # 2) 来自 intents.yaml（若存在）
    try:
        intents_path = ProjectPaths(workspace_root, pid).intents_file()
        if intents_path.exists():
            import yaml  # type: ignore
            from clude_code.orchestrator.registry.schema import ProjectConfig

            data = yaml.safe_load(intents_path.read_text(encoding="utf-8")) or {}
            cfg = ProjectConfig.model_validate(data).normalize()

            def _collect_stage(stage_obj: Any) -> None:
                if not stage_obj:
                    return
                for layer in ("base", "domain", "task"):
                    l = getattr(stage_obj, layer, None)
                    if l and getattr(l, "ref", None):
                        refs.add(str(getattr(l, "ref")).strip())

            if cfg.prompts:
                for stage_name in cfg.prompts.model_fields.keys():  # type: ignore[attr-defined]
                    _collect_stage(getattr(cfg.prompts, stage_name, None))
            for it in cfg.intents:
                if it.prompts:
                    for stage_name in it.prompts.model_fields.keys():  # type: ignore[attr-defined]
                        _collect_stage(getattr(it.prompts, stage_name, None))
    except Exception:
        # 校验命令不应因 intents.yaml 解析失败崩溃
        pass

    # 3) 命令行指定 ref
    if ref:
        refs = {ref.strip()}
    # 4) 若没有任何来源（既没有 intents.yaml、也没有 prompt_versions.json），默认校验 prompts 全量文件（新工程强约束）
    if not refs:
        for p in _prompts_root().rglob("*"):
            if not p.is_file():
                continue
            if p.suffix.lower() not in {".j2", ".md"}:
                continue
            rel = str(p.relative_to(_prompts_root())).replace("\\", "/")
            # 只校验“真正的 prompt 文件”目录（避免把 README/实现代码当成 prompt）
            # 目录结构对齐 agent_design_v_1.0.md：system/* + user/*
            if not (rel.startswith("system/") or rel.startswith("user/")):
                continue
            refs.add(rel)

    root = _prompts_root()
    errors: list[str] = []

    # 额外布局健壮性提示：避免“看起来两套体系并存”的误解
    # 说明：这些目录为历史遗留（可为空），不参与校验与运行期引用。
    legacy_dirs = ["base", "domains", "tasks"]
    for d in legacy_dirs:
        try:
            if (root / d).exists():
                typer.echo(f"WARN: 发现遗留目录 prompts/{d}/（当前已废弃，仅保留以避免历史提交抖动；请勿放置新 prompt）")
        except Exception:
            pass

    def _validate_one(r: str) -> None:
        rel = r.strip()
        if not rel:
            return
        abs_path = (root / rel).resolve()
        if root not in abs_path.parents and abs_path != root:
            errors.append(f"{rel}: ref 路径越界（拒绝）")
            return
        if not abs_path.exists():
            errors.append(f"{rel}: 文件不存在: {abs_path}")
            return

        meta, _body, has_fm, fm_err = _read_yaml_front_matter(abs_path)
        if not has_fm:
            errors.append(f"{rel}: 缺少 YAML front matter（必须有 --- ... ---）")
        if fm_err:
            errors.append(f"{rel}: {fm_err}")
        if has_fm and not fm_err:
            errors.extend([f"{rel}: {e}" for e in _validate_front_matter(meta)])

        # 校验版本化文件：current/previous（如果存在）
        it = prompts_map.get(rel) or {}
        for key in ("current", "previous"):
            v = (it.get(key) or "").strip() if isinstance(it, dict) else ""
            if not v:
                continue
            vref = _resolve_versioned_ref(rel, v)
            vpath = (root / vref).resolve()
            if not vpath.exists():
                errors.append(f"{rel}: {key}={v} 但版本文件不存在: {vref}")
                continue
            vmeta, _b, v_has, v_err = _read_yaml_front_matter(vpath)
            if not v_has:
                errors.append(f"{vref}: 缺少 YAML front matter")
            if v_err:
                errors.append(f"{vref}: {v_err}")
            if v_has and not v_err:
                errors.extend([f"{vref}: {e}" for e in _validate_front_matter(vmeta, expected_version=v)])

    for r in sorted(refs):
        _validate_one(r)

    if errors:
        typer.echo("VALIDATE_FAILED:")
        for e in errors:
            typer.echo(f"- {e}")
        raise typer.Exit(code=2)

    typer.echo(f"VALIDATE_OK: {len(refs)} refs")


