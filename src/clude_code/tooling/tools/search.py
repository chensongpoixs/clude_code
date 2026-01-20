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
    # 说明：
    # - 本项目按你的要求：codesearch **只实现网络搜索代码**（Grep.app）
    # - 不提供 local_rag（本地检索）能力
    config = get_search_config()
    if not config.enabled:
        _logger.warning("[CodeSearch] 代码搜索工具已被禁用")
        return ToolResult(False, error={"code": "E_TOOL_DISABLED", "message": "search tool is disabled"})

    timeout_s = int(getattr(config, "timeout_s", 30) or 30)
    max_results = int(getattr(config, "max_results", 50) or 50)

    # budget：粗略将 tokens 预算映射到字符上限（避免输出过大）
    max_chars_budget = max(int(tokens_num or 0) * 4, 2000)

    r = _codesearch_via_grep_app(
        query=query,
        timeout_s=timeout_s,
        max_results=min(max_results, 50),
        max_chars_budget=max_chars_budget,
    )
    if r.ok:
        if r.payload is None:
            r.payload = {}
        r.payload["provider"] = "grep_app"
    return r


def _codesearch_via_grep_app(*, query: str, timeout_s: int, max_results: int, max_chars_budget: int) -> ToolResult:
    config = get_search_config()
    if not getattr(config, "grep_app_enabled", True):
        return ToolResult(ok=False, error={"code": "E_PROVIDER_DISABLED", "message": "grep_app disabled"})

    base_url = (getattr(config, "grep_app_base_url", "") or "").rstrip("/")
    endpoint = getattr(config, "grep_app_endpoint", "/api/search") or "/api/search"
    if not base_url:
        return ToolResult(ok=False, error={"code": "E_NOT_CONFIGURED", "message": "grep_app_base_url is empty"})

    # 说明：grep.app 的返回结构可能随版本变化，这里做“宽松解析” + “异常降级”
    if not (base_url.startswith("http://") or base_url.startswith("https://")):
        return ToolResult(ok=False, error={"code": "E_NOT_CONFIGURED", "message": f"invalid grep_app_base_url: {base_url}"})
    if not endpoint.startswith("/"):
        endpoint = "/" + endpoint

    url = f"{base_url}{endpoint}"
    params = {"q": query}
    headers = {
        "Accept": "application/json",
        # 避免被部分服务当作机器人拦截；不输出到日志以免刷屏
        "User-Agent": "clude-code/0.1 (codesearch; grep.app)",
    }

    # 轻量重试：处理临时性网络抖动/限流
    tries = 2
    last_exc: Exception | None = None
    last_status: int | None = None
    body_text: str | None = None
    for attempt in range(tries):
        try:
            with httpx.Client(timeout=max(float(timeout_s or 0), 1.0)) as client:
                resp = client.get(url, params=params, headers=headers)
            last_status = resp.status_code
            body_text = resp.text

            if resp.status_code in (429, 502, 503, 504) and attempt < tries - 1:
                time.sleep(0.35 * (attempt + 1))
                continue

            if resp.status_code >= 400:
                return ToolResult(
                    ok=False,
                    error={
                        "code": "E_PROVIDER_HTTP",
                        "message": f"grep_app http {resp.status_code}",
                        "details": {"status_code": resp.status_code, "url": url},
                    },
                )

            try:
                data = resp.json()
            except Exception:
                return ToolResult(
                    ok=False,
                    error={
                        "code": "E_BAD_RESPONSE",
                        "message": "grep_app returned non-json response",
                        "details": {
                            "status_code": resp.status_code,
                            "content_type": resp.headers.get("content-type"),
                            "text_preview": (body_text or "")[:300],
                        },
                    },
                )
            break
        except Exception as e:
            last_exc = e
            if attempt < tries - 1:
                time.sleep(0.25 * (attempt + 1))
                continue
            return ToolResult(ok=False, error={"code": "E_PROVIDER_FAILED", "message": str(e), "provider": "grep_app"})

    # 宽松解析命中列表：优先 hits.hits（即使为空列表也要保留），其次 results/items
    hits: Any = None
    if isinstance(data, dict):
        hits_obj = data.get("hits")
        if isinstance(hits_obj, dict) and "hits" in hits_obj:
            hits = hits_obj.get("hits")
        elif "results" in data:
            hits = data.get("results")
        elif "items" in data:
            hits = data.get("items")
    if not isinstance(hits, list):
        return ToolResult(
            ok=False,
            error={
                "code": "E_BAD_RESPONSE",
                "message": "grep_app response missing hits list",
                "details": {"status_code": last_status, "url": url},
            },
        )

    results: list[dict[str, Any]] = []
    used_chars = 0
    for h in hits:
        if not isinstance(h, dict):
            continue
        repo = (h.get("repo") or {}) if isinstance(h.get("repo"), dict) else {}
        path_obj = (h.get("path") or {}) if isinstance(h.get("path"), dict) else {}
        content_obj = (h.get("content") or {}) if isinstance(h.get("content"), dict) else {}

        repo_name = str(repo.get("name") or "")
        file_path = str(path_obj.get("path") or h.get("path") or "")
        snippet = str(content_obj.get("snippet") or content_obj.get("text") or h.get("snippet") or "")
        language = str(h.get("lang") or h.get("language") or "")
        score = h.get("score") or h.get("_score") or None

        if not file_path and not snippet:
            continue

        # budget 控制：避免返回过大
        if used_chars + len(snippet) > max_chars_budget:
            snippet = snippet[: max(0, max_chars_budget - used_chars)]

        used_chars += len(snippet)
        results.append(
            {
                "repo": repo_name,
                "path": file_path,
                "language": language,
                "code": snippet,
                "explanation": "来自 Grep.app 的开源代码匹配片段（可能需要你根据项目上下文改造）。",
                "relevance_score": score,
                "url": f"{base_url}/search?q={query}",
            }
        )
        if len(results) >= max_results or used_chars >= max_chars_budget:
            break

    if not results:
        return ToolResult(ok=False, error={"code": "E_NO_RESULTS", "message": "grep_app returned no results"})

    return ToolResult(ok=True, payload={"query": query, "results": results, "total_results": len(results)})