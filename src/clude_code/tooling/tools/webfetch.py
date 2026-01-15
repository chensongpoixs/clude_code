"""
WebFetch tool - 获取网页内容

从指定的URL获取网页内容，支持不同的格式（markdown, text, html）。
"""
from __future__ import annotations

import requests
import time
from typing import Literal, Optional
from urllib.parse import urlparse

from clude_code.tooling.types import ToolResult, ToolError


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
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(response.text, 'html.parser')
            content = soup.get_text(separator='\n', strip=True)
        elif format == "markdown":
            # 使用html2text转换
            import html2text
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

    except requests.Timeout:
        return ToolResult(
            ok=False,
            error={
                "message": f"Request timeout after {timeout} seconds",
                "code": "WEBFETCH_TIMEOUT"
            }
        )
    except requests.RequestException as e:
        return ToolResult(
            ok=False,
            error={
                "message": f"Network error: {str(e)}",
                "code": "WEBFETCH_NETWORK_ERROR"
            }
        )
    except Exception as e:
        return ToolResult(
            ok=False,
            error={
                "message": f"Failed to fetch web content: {str(e)}",
                "code": "WEBFETCH_FAILED"
            }
        )