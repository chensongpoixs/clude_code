"""
WebFetch tool - 获取网页内容

从指定的URL获取网页内容，支持不同的格式（markdown, text, html）。
"""
from __future__ import annotations

import time
from typing import Literal
from urllib.parse import urlparse

import httpx
import re
from clude_code.tooling.types import ToolResult, ToolError
from ..logger_helper import get_tool_logger
from ...config.tools_config import get_web_config

# 工具模块 logger（延迟初始化）
_logger = get_tool_logger(__name__)

def fetch_web_content(
    url: str,
    format: Literal["markdown", "text"] = "markdown",
    timeout: int = 30
) -> ToolResult:
    # 检查工具是否启用
    config = get_web_config()
    if not config.enabled:
        _logger.warning("[WebFetch] 网页抓取工具已被禁用")
        return ToolResult(False, error={"code": "E_TOOL_DISABLED", "message": "web tool is disabled"})

    _logger.debug(f"[WebFetch] 开始获取网页: url={url}, format={format}, timeout={timeout}")
    try:
        # 验证URL
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            _logger.warning(f"[WebFetch] 无效的 URL 格式: {url}")
            return ToolResult(ok=False, error={"code": "E_INVALID_URL", "message": "invalid url format"})
        if parsed.scheme not in {"http", "https"}:
            return ToolResult(ok=False, error={"code": "E_INVALID_URL", "message": f"unsupported scheme: {parsed.scheme}"})

        # 使用配置上限控制内容大小（避免 UI/上下文被打爆）
        max_len = int(getattr(config, "max_content_length", 50000) or 50000)
        if max_len < 1000:
            max_len = 1000

        headers = {"User-Agent": "clude-code/0.1 (webfetch)", "Accept": "*/*"}

        # 自动升级到 HTTPS（如果适用）+ 轻量重试（429/5xx）
        candidates = [url]
        if parsed.scheme == "http":
            candidates = [url.replace("http://", "https://", 1), url]

        response: httpx.Response | None = None
        last_exc: Exception | None = None
        for u in candidates:
            for attempt in range(2):
                try:
                    with httpx.Client(timeout=max(float(timeout or 0), 1.0), follow_redirects=True) as client:
                        r = client.get(u, headers=headers)
                    if r.status_code in (429, 502, 503, 504) and attempt == 0:
                        time.sleep(0.35)
                        continue
                    response = r
                    break
                except Exception as e:
                    last_exc = e
                    if attempt == 0:
                        time.sleep(0.25)
                        continue
            if response is not None:
                break

        if response is None:
            return ToolResult(ok=False, error={"code": "WEBFETCH_FAILED", "message": str(last_exc or "request failed")})
        if response.status_code >= 400:
            return ToolResult(
                ok=False,
                error={"code": "WEBFETCH_HTTP", "message": f"http {response.status_code}", "details": {"url": url}},
            )

        # 根据格式处理内容
        # if format == "html":
        #     content = response.text
        # elif format == "text":
        if format == "text":
            # 简单的HTML到文本转换
            try:
                from bs4 import BeautifulSoup  # type: ignore
                soup = BeautifulSoup(response.text, "html.parser")
                content = soup.get_text(separator="\n", strip=True)
            except Exception:
                # 兜底：无 bs4 时尽量提供“可读文本”，避免工具直接不可用
                html = response.text or ""
                txt = re.sub(r"(?is)<script.*?>.*?</script>", "", html)
                txt = re.sub(r"(?is)<style.*?>.*?</style>", "", txt)
                txt = re.sub(r"(?s)<[^>]+>", "\n", txt)
                txt = re.sub(r"\n{3,}", "\n\n", txt)
                content = txt.strip()
        elif format == "markdown":
            # 使用html2text转换
            try:
                import html2text  # type: ignore
                h = html2text.HTML2Text()
                h.ignore_links = False
                h.ignore_images = False
                h.ignore_tables = False
                content = h.handle(response.text)
            except Exception:
                # 兜底：无 html2text 时退化为 text（避免工具不可用）
                html = response.text or ""
                txt = re.sub(r"(?is)<script.*?>.*?</script>", "", html)
                txt = re.sub(r"(?is)<style.*?>.*?</style>", "", txt)
                txt = re.sub(r"(?s)<[^>]+>", "\n", txt)
                txt = re.sub(r"\n{3,}", "\n\n", txt)
                content = txt.strip()
        else:
            return ToolResult(ok=False, error={"code": "E_INVALID_ARGS", "message": f"unsupported format: {format}"})

        truncated = False
        if len(content) > max_len:
            content = content[:max_len] + "\n\n[Content truncated due to length]"
            truncated = True

        result_data = {
            "url": url,
            "format": format,
            "content": content,
            "status_code": response.status_code,
            "content_length": len(content),
            "truncated": truncated,
        }

        return ToolResult(
            ok=True,
            payload=result_data
        )

    except Exception as e:
        # best-effort 分类（不依赖 requests）
        return ToolResult(
            ok=False,
            error={
                "message": f"Failed to fetch web content: {str(e)}",
                "code": "WEBFETCH_FAILED"
            }
        )