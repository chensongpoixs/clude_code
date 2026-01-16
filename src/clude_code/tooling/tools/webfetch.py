"""
WebFetch tool - 获取网页内容

从指定的URL获取网页内容，支持不同的格式（markdown, text, html）。
"""
from __future__ import annotations

import time
from typing import Literal, Optional
from urllib.parse import urlparse

from clude_code.tooling.types import ToolResult, ToolError

try:
    import requests  # type: ignore
except Exception:
    # 可选依赖：缺失时不应阻塞整个 CLI 导入链路
    requests = None  # type: ignore


def fetch_web_content(
    url: str,
    format: Literal["markdown", "text", "html"] = "markdown",
    timeout: int = 30
) -> ToolResult:
    """
    获取网页内容工具

    Args:
        url: 要获取的URL
        format: 返回格式 (markdown/text/html)
        timeout: 请求超时时间（秒）

    Returns:
        ToolResult: 包含网页内容的工具结果
    """
    if requests is None:
        return ToolResult(
            ok=False,
            error={
                "code": "E_DEP_MISSING",
                "message": "requests 未安装，无法进行 webfetch。请安装依赖：pip install requests",
            },
        )
    try:
        # 验证URL
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError("Invalid URL format")

        # 自动升级到HTTPS（如果适用）
        if parsed.scheme == "http":
            https_url = url.replace("http://", "https://", 1)
            try:
                # 先尝试HTTPS
                response = requests.get(https_url, timeout=timeout)
            except requests.RequestException:
                # 如果HTTPS失败，回退到HTTP
                response = requests.get(url, timeout=timeout)
        else:
            response = requests.get(url, timeout=timeout)

        response.raise_for_status()

        # 根据格式处理内容
        if format == "html":
            content = response.text
        elif format == "text":
            # 简单的HTML到文本转换
            try:
                from bs4 import BeautifulSoup  # type: ignore
            except Exception:
                return ToolResult(
                    ok=False,
                    error={
                        "code": "E_DEP_MISSING",
                        "message": "bs4 未安装，无法将 HTML 转为 text。请安装依赖：pip install beautifulsoup4",
                    },
                )
            soup = BeautifulSoup(response.text, 'html.parser')
            content = soup.get_text(separator='\n', strip=True)
        elif format == "markdown":
            # 使用html2text转换
            try:
                import html2text  # type: ignore
            except Exception:
                return ToolResult(
                    ok=False,
                    error={
                        "code": "E_DEP_MISSING",
                        "message": "html2text 未安装，无法将 HTML 转为 markdown。请安装依赖：pip install html2text",
                    },
                )
            h = html2text.HTML2Text()
            h.ignore_links = False
            h.ignore_images = False
            h.ignore_tables = False
            content = h.handle(response.text)
        else:
            raise ValueError(f"Unsupported format: {format}")

        # 如果内容过长，进行摘要
        max_length = 50000
        if len(content) > max_length:
            content = content[:max_length] + "\n\n[Content truncated due to length]"

        result_data = {
            "url": url,
            "format": format,
            "content": content,
            "status_code": response.status_code,
            "content_length": len(content)
        }

        return ToolResult(
            ok=True,
            payload=result_data
        )

    except Exception as e:
        # requests 的异常类型在不同版本可能不同，这里统一做 best-effort 分类
        try:
            if hasattr(requests, "Timeout") and isinstance(e, requests.Timeout):  # type: ignore[attr-defined]
                return ToolResult(
                    ok=False,
                    error={
                        "message": f"Request timeout after {timeout} seconds",
                        "code": "WEBFETCH_TIMEOUT"
                    }
                )
            if hasattr(requests, "RequestException") and isinstance(e, requests.RequestException):  # type: ignore[attr-defined]
                return ToolResult(
                    ok=False,
                    error={
                        "message": f"Network error: {str(e)}",
                        "code": "WEBFETCH_NETWORK_ERROR"
                    }
                )
        except Exception:
            # 分类失败不影响返回
            pass
        return ToolResult(
            ok=False,
            error={
                "message": f"Failed to fetch web content: {str(e)}",
                "code": "WEBFETCH_FAILED"
            }
        )