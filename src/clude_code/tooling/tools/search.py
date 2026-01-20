"""
WebSearch tool - 网页搜索工具

使用外部搜索API进行网页搜索，提供实时信息。
"""
from __future__ import annotations

import json
import time
from typing import Any, Literal

import httpx
from clude_code.tooling.types import ToolResult, ToolError
from ..logger_helper import get_tool_logger
from ...config.tools_config import get_search_config

# 工具模块 logger（延迟初始化）
_logger = get_tool_logger(__name__)

def _normalize_results(query: str, items: list[dict[str, Any]], num_results: int) -> ToolResult:
    results: list[dict[str, Any]] = []
    for it in items[: max(0, num_results)]:
        title = str(it.get("title") or it.get("name") or "").strip()
        url = str(it.get("url") or it.get("link") or "").strip()
        snippet = str(it.get("snippet") or it.get("description") or it.get("content") or "").strip()
        score = it.get("score")
        out: dict[str, Any] = {"title": title, "url": url, "snippet": snippet}
        if score is not None:
            out["score"] = score
        results.append(out)

    return ToolResult(
        ok=True,
        payload={
            "query": query,
            "results": results,
            "total_results": len(results),
        },
    )


def _websearch_via_open_websearch_mcp(
    query: str,
    num_results: int,
    timeout_s: int,
) -> ToolResult:
    config = get_search_config()
    if not getattr(config, "open_websearch_mcp_enabled", True):
        return ToolResult(ok=False, error={"code": "E_PROVIDER_DISABLED", "message": "open_websearch_mcp disabled"})

    base_url = (getattr(config, "open_websearch_mcp_base_url", "") or "").rstrip("/")
    endpoint = getattr(config, "open_websearch_mcp_endpoint", "/search") or "/search"
    if not base_url:
        return ToolResult(ok=False, error={"code": "E_NOT_CONFIGURED", "message": "open_websearch_mcp_base_url is empty"})

    url = f"{base_url}{endpoint}"
    headers: dict[str, str] = {"Content-Type": "application/json"}
    api_key = getattr(config, "open_websearch_mcp_api_key", "") or ""
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {"query": query, "num_results": num_results}
    with httpx.Client(timeout=timeout_s) as client:
        resp = client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()

    # 兼容不同返回结构
    items = data.get("results") or data.get("items") or data.get("data") or []
    if isinstance(items, list):
        return _normalize_results(query, items, num_results)
    return ToolResult(ok=False, error={"code": "E_BAD_RESPONSE", "message": "open_websearch_mcp response missing results list"})


def _websearch_via_serper(
    query: str,
    num_results: int,
    timeout_s: int,
) -> ToolResult:
    config = get_search_config()
    api_key = getattr(config, "serper_api_key", "") or ""
    if not api_key:
        return ToolResult(ok=False, error={"code": "E_NOT_CONFIGURED", "message": "serper_api_key is empty"})

    headers = {"X-API-KEY": api_key, "Content-Type": "application/json"}
    payload = {
        "q": query,
        "num": num_results,
        "gl": getattr(config, "serper_gl", "cn"),
        "hl": getattr(config, "serper_hl", "zh-cn"),
    }
    with httpx.Client(timeout=timeout_s) as client:
        resp = client.post("https://google.serper.dev/search", headers=headers, content=json.dumps(payload))
        resp.raise_for_status()
        data = resp.json()
    items = data.get("organic") or []
    if isinstance(items, list):
        return _normalize_results(query, items, num_results)
    return ToolResult(ok=False, error={"code": "E_BAD_RESPONSE", "message": "serper response missing organic list"})


"""
网页搜索（Web Search）
@author chensong（chensong）
@date 2026-01-20
@brief 通过 Open-WebSearch MCP / Serper 搜索资料（Prefer MCP, fallback Serper）

规则（Rules）：
- Provider 选择由配置 `search.websearch_providers` 决定（优先级列表）。
- 默认优先 Open-WebSearch MCP；失败（网络/超时/配置缺失）自动回退 Serper。
- 日志只写摘要，敏感信息（API Key）不得输出明文。
"""
def websearch(
    query: str,
    num_results: int = 8,
    livecrawl: Literal["fallback", "preferred"] = "fallback",
    search_type: Literal["auto", "fast", "deep"] = "auto",
    context_max_chars: int = 10000
) -> ToolResult:
    # 检查工具是否启用
    config = get_search_config()
    if not config.enabled:
        _logger.warning("[WebSearch] 网页搜索工具已被禁用")
        return ToolResult(False, error={"code": "E_TOOL_DISABLED", "message": "search tool is disabled"})

    _logger.debug(f"[WebSearch] 开始搜索: query={query}, num_results={num_results}, search_type={search_type}")
    providers = getattr(config, "websearch_providers", None) or ["open_websearch_mcp", "serper"]
    timeout_s = int(getattr(config, "timeout_s", 30) or 30)
    last_error: dict[str, Any] | None = None

    for p in providers:
        try:
            if p == "open_websearch_mcp":
                r = _websearch_via_open_websearch_mcp(query=query, num_results=num_results, timeout_s=timeout_s)
            elif p == "serper":
                r = _websearch_via_serper(query=query, num_results=num_results, timeout_s=timeout_s)
            else:
                continue

            if r.ok:
                # 补齐元信息（保持旧接口字段，兼容 UI/LLM 的消费方式）
                if r.payload is None:
                    r.payload = {}
                r.payload.update(
                    {
                        "search_type": search_type,
                        "livecrawl": livecrawl,
                        "context_max_chars": context_max_chars,
                        "provider": p,
                    }
                )
                _logger.info(f"[WebSearch] 搜索完成: provider={p}, query={query}, 返回 {len(r.payload.get('results', []) or [])} 个结果")
                return r

            last_error = r.error
            _logger.warning(f"[WebSearch] provider 失败，将回退: provider={p}, error={r.error}")
        except Exception as e:
            last_error = {"code": "E_PROVIDER_FAILED", "message": str(e), "provider": p}
            # 规范要求：控制台只输出可读摘要，避免 traceback 刷屏；详细堆栈交由 file-only/更高层处理。
            _logger.warning(f"[WebSearch] provider 异常，将回退: provider={p}, error={e}")

    return ToolResult(ok=False, error=last_error or {"code": "WEBSEARCH_FAILED", "message": "all providers failed"})


def codesearch(
    query: str,
    tokens_num: int = 5000
) -> ToolResult:
    # 说明：当前 codesearch 仍为 mock（待接入真实代码检索源）。
    try:
        # 这里需要配置实际的代码搜索API（例如Exa Code API）
        # 现在返回模拟结果

        mock_results = {
            "query": query,
            "results": [
                {
                    "language": "python",
                    "code": "def example_function():\n    return 'Hello World'",
                    "explanation": f"Example code result for query: {query}",
                    "relevance_score": 0.92
                },
                {
                    "language": "javascript",
                    "code": "function example() {\n    return 'Hello World';\n}",
                    "explanation": f"JavaScript implementation related to {query}",
                    "relevance_score": 0.85
                }
            ],
            "tokens_used": min(tokens_num, 2500),
            "total_available": tokens_num
        }

        return ToolResult(
            ok=True,
            payload=mock_results
        )

    except Exception as e:
        return ToolResult(
            ok=False,
            error={
                "message": f"Code search failed: {str(e)}",
                "code": "CODESEARCH_FAILED"
            }
        )