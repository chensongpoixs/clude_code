"""
厂商配置命令（CLI）：`clude providers ...`

目标：
- 命令行配置每个厂商的 base_url / api_key / default_model / extra 等
- 保存到配置文件（默认 ~/.clude/.clude.yaml）
- 输出时对 api_key 做脱敏
"""

from __future__ import annotations

import typer
from typing import Any

from clude_code.config import get_config_manager
from clude_code.config.config import ProviderConfigItem, normalize_provider_id

providers_app = typer.Typer(help="LLM 厂商配置与查询（写入 ~/.clude/.clude.yaml）")


def _mask(s: str) -> str:
    if not s:
        return ""
    if len(s) <= 8:
        return "***"
    return f"{s[:4]}***{s[-4:]}"


def _parse_extra(extra: list[str] | None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if not extra:
        return out
    for kv in extra:
        if "=" not in kv:
            raise typer.BadParameter(f"--extra 需要 key=value 格式，收到: {kv!r}")
        k, v = kv.split("=", 1)
        k = k.strip()
        v = v.strip()
        if not k:
            raise typer.BadParameter(f"--extra key 不能为空: {kv!r}")
        # 尝试做轻量类型转换
        if v.lower() in {"true", "false"}:
            out[k] = (v.lower() == "true")
        else:
            try:
                if "." in v:
                    out[k] = float(v)
                else:
                    out[k] = int(v)
            except Exception:
                out[k] = v
    return out


@providers_app.command("set")
def set_provider(
    provider_id: str = typer.Argument(..., help="厂商 ID（例如 llama_cpp/openai/anthropic/...）"),
    base_url: str = typer.Option("", "--base-url", help="API Base URL（不填则不修改）"),
    api_key: str = typer.Option("", "--api-key", help="API Key（不填则不修改；会写入配置文件）"),
    enabled: bool | None = typer.Option(None, "--enabled/--disabled", help="是否启用该厂商（不指定则不修改）"),
    default_model: str = typer.Option("", "--default-model", help="默认模型（不填则不修改）"),
    timeout_s: int = typer.Option(0, "--timeout-s", help="超时秒数（0 表示不修改）"),
    api_version: str = typer.Option("", "--api-version", help="API 版本（如 Azure；不填则不修改）"),
    organization: str = typer.Option("", "--organization", help="组织 ID（如 OpenAI；不填则不修改）"),
    extra: list[str] = typer.Option(None, "--extra", help="额外参数 key=value，可重复传入"),
    set_default: bool = typer.Option(False, "--set-default", help="同时把 providers.default 设为该厂商"),
) -> None:
    """
    设置单个厂商配置并写入配置文件。

    示例：
      clude providers set openai --base-url https://api.openai.com/v1 --api-key sk-xxx --enabled --default-model gpt-4o
      clude providers set llama_cpp --base-url http://127.0.0.1:8899 --enabled --extra n_ctx=32768 --extra api_mode=openai_compat --set-default
    """
    pid = normalize_provider_id(provider_id.strip())
    cm = get_config_manager()
    cfg = cm.config

    # 获取现有配置（不存在则创建）
    current = cfg.providers.get_item(pid) if hasattr(cfg.providers, "get_item") else None
    if current is None:
        current = ProviderConfigItem()

    # 应用变更
    if enabled is not None:
        current.enabled = bool(enabled)
    if base_url:
        current.base_url = base_url.strip()
    if api_key:
        current.api_key = api_key.strip()
    if default_model:
        current.default_model = default_model.strip()
    if timeout_s:
        current.timeout_s = int(timeout_s)
    if api_version:
        current.api_version = api_version.strip()
    if organization:
        current.organization = organization.strip()

    extra_kv = _parse_extra(extra)
    if extra_kv:
        current.extra.update(extra_kv)

    # 写回 providers.items
    if not hasattr(cfg.providers, "items") or not isinstance(cfg.providers.items, dict):
        cfg.providers.items = {}
    cfg.providers.items[pid] = current

    # 可选：设置默认
    if set_default:
        cfg.providers.default = pid
        cfg.llm.provider = pid  # legacy 同步，降低困惑

    cm.save_config()

    # 输出结果（脱敏）
    typer.echo(f"✓ 已保存厂商配置: {pid}")
    typer.echo(f"  enabled={current.enabled}")
    typer.echo(f"  base_url={current.base_url}")
    typer.echo(f"  default_model={current.default_model}")
    typer.echo(f"  timeout_s={current.timeout_s}")
    if current.api_version:
        typer.echo(f"  api_version={current.api_version}")
    if current.organization:
        typer.echo(f"  organization={current.organization}")
    typer.echo(f"  api_key={_mask(current.api_key)}")
    if current.extra:
        typer.echo(f"  extra={current.extra}")
    if set_default:
        typer.echo(f"  providers.default={pid}")


@providers_app.command("show")
def show_provider(
    provider_id: str = typer.Argument("", help="厂商 ID；不填则列出所有厂商配置摘要"),
) -> None:
    """查看厂商配置（脱敏）。"""
    cm = get_config_manager()
    cfg = cm.config

    if not provider_id:
        pub = cfg.providers.to_public_dict(include_disabled=True)
        default_pid = pub.get("default", "")
        typer.echo(f"providers.default={default_pid}")
        for pid in sorted([k for k in pub.keys() if k != "default"]):
            item = pub.get(pid, {}) or {}
            typer.echo(f"- {pid}: enabled={item.get('enabled')} base_url={item.get('base_url')} default_model={item.get('default_model')} api_key={item.get('api_key')}")
        return

    pid = normalize_provider_id(provider_id.strip())
    pub = cfg.providers.to_public_dict(include_disabled=True)
    item = pub.get(pid)
    if item is None:
        typer.echo(f"未找到厂商配置: {pid}")
        return
    typer.echo(f"{pid}（脱敏）:")
    for k, v in item.items():
        typer.echo(f"- {k}: {v}")


