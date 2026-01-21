"""
WebFetch tool - 获取网页内容并缓存为 Markdown

功能特性：
- 抓取网页内容并转换为 Markdown 格式
- 本地缓存到配置指定目录（默认 .clude/markdown/）
- 文件名以文档标题命名
- 缓存有效期默认 7 天（可配置），自动检查过期
- 优先返回本地缓存，无缓存则抓取
"""
from __future__ import annotations

import hashlib
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

import httpx

from clude_code.tooling.types import ToolResult
from ..logger_helper import get_tool_logger
from ...config.tools_config import get_web_config

# 工具模块 logger（延迟初始化）
_logger = get_tool_logger(__name__)

def _sanitize_filename(title: str, *, max_len: int) -> str:
    """
    将标题转换为安全的文件名。
    
    - 移除/替换非法字符
    - 限制长度
    - 处理空白和特殊情况
    """
    if not title:
        return "untitled"
    
    # 移除或替换非法文件名字符
    # Windows 禁止: \ / : * ? " < > |
    # 同时处理控制字符和多余空白
    sanitized = re.sub(r'[\\/:*?"<>|\x00-\x1f]', '_', title)
    sanitized = re.sub(r'\s+', '_', sanitized)
    sanitized = re.sub(r'_+', '_', sanitized)
    sanitized = sanitized.strip('_. ')
    
    # 限制长度（为 .md 扩展名预留空间）
    try:
        max_len = int(max_len or 0)
    except Exception:
        max_len = 100
    if max_len < 16:
        max_len = 16
    if len(sanitized) > max_len:
        sanitized = sanitized[:max_len]
    
    return sanitized if sanitized else "untitled"


def _extract_title_from_html(html: str) -> str:
    """从 HTML 中提取标题。"""
    # 尝试匹配 <title> 标签
    match = re.search(r'<title[^>]*>([^<]+)</title>', html, re.IGNORECASE)
    if match:
        title = match.group(1).strip()
        # 解码 HTML 实体
        title = re.sub(r'&amp;', '&', title)
        title = re.sub(r'&lt;', '<', title)
        title = re.sub(r'&gt;', '>', title)
        title = re.sub(r'&quot;', '"', title)
        title = re.sub(r'&#39;', "'", title)
        title = re.sub(r'&nbsp;', ' ', title)
        return title
    
    # 尝试匹配 <h1> 标签
    match = re.search(r'<h1[^>]*>([^<]+)</h1>', html, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    
    # 尝试匹配 og:title meta 标签
    match = re.search(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']', html, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    
    return ""


def _url_to_cache_key(url: str) -> str:
    """将 URL 转换为缓存键（用于索引文件查找）。"""
    return hashlib.md5(url.encode('utf-8')).hexdigest()[:16]


def _get_cache_dir(workspace_root: str | None, *, cache_dir: str) -> Path:
    """获取缓存目录路径。"""
    p = (cache_dir or "").strip()
    if not p:
        p = ".clude/markdown"
    try:
        # 支持绝对路径
        cp = Path(p)
        if cp.is_absolute():
            return cp
    except Exception:
        # 回退为相对路径
        pass
    base = Path(workspace_root) if workspace_root else Path.cwd()
    return base / p


def _ensure_cache_dir(cache_dir: Path) -> bool:
    """确保缓存目录存在。返回是否成功。"""
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        return True
    except Exception as e:
        _logger.warning(f"[WebFetch] 无法创建缓存目录 {cache_dir}: {e}")
        return False


def _parse_cache_metadata(content: str) -> dict | None:
    """
    从 Markdown 文件的 YAML front matter 中解析元数据。
    
    格式:
    ---
    url: https://example.com
    title: Example Title
    fetched_at: 2024-01-20T12:00:00
    expires_at: 2024-01-27T12:00:00
    cache_key: abc123
    ---
    """
    if not content.startswith('---'):
        return None
    
    # 查找结束标记
    end_match = re.search(r'\n---\n', content[3:])
    if not end_match:
        return None
    
    front_matter = content[3:end_match.start() + 3]
    metadata = {}
    
    for line in front_matter.strip().split('\n'):
        if ':' in line:
            key, value = line.split(':', 1)
            metadata[key.strip()] = value.strip()
    
    return metadata


def _build_cache_content(url: str, title: str, markdown_content: str, cache_key: str) -> str:
    """构建带元数据的缓存文件内容。"""
    now = datetime.now()
    cfg = get_web_config()
    try:
        expiry_days = int(getattr(cfg, "cache_expiry_days", 7) or 7)
    except Exception:
        expiry_days = 7
    expiry_days = max(1, min(365, expiry_days))
    expires = now + timedelta(days=expiry_days)
    
    front_matter = f"""---
url: {url}
title: {title}
fetched_at: {now.isoformat()}
expires_at: {expires.isoformat()}
cache_key: {cache_key}
---

"""
    return front_matter + markdown_content


def _find_cache_file(cache_dir: Path, cache_key: str, *, cfg: object) -> Path | None:
    """
    查找匹配缓存键的文件。
    
    遍历缓存目录，读取每个 .md 文件的元数据，匹配 cache_key。
    """
    if not cache_dir.exists():
        return None
    
    # 优化：先尝试索引文件（如果存在）
    index_enabled = bool(getattr(cfg, "cache_index_enabled", True))
    index_name = str(getattr(cfg, "cache_index_filename", ".cache_index") or ".cache_index")
    index_file = cache_dir / index_name
    if index_enabled and index_file.exists():
        try:
            index_content = index_file.read_text(encoding='utf-8')
            for line in index_content.strip().split('\n'):
                if line.startswith(cache_key + ':'):
                    filename = line.split(':', 1)[1].strip()
                    cached_path = cache_dir / filename
                    if cached_path.exists():
                        return cached_path
        except Exception:
            pass
    
    # 回退：遍历目录查找
    try:
        scan_prefix = int(getattr(cfg, "cache_scan_prefix_bytes", 2000) or 2000)
    except Exception:
        scan_prefix = 2000
    scan_prefix = max(256, min(20000, scan_prefix))
    try:
        for file in cache_dir.glob('*.md'):
            try:
                content = file.read_text(encoding='utf-8')[:scan_prefix]  # 只读取开头部分
                metadata = _parse_cache_metadata(content)
                if metadata and metadata.get('cache_key') == cache_key:
                    return file
            except Exception:
                continue
    except Exception as e:
        _logger.debug(f"[WebFetch] 缓存目录遍历失败: {e}")
    
    return None


def _update_cache_index(cache_dir: Path, cache_key: str, filename: str, *, cfg: object) -> None:
    """更新缓存索引文件。"""
    if not bool(getattr(cfg, "cache_index_enabled", True)):
        return
    index_name = str(getattr(cfg, "cache_index_filename", ".cache_index") or ".cache_index")
    index_file = cache_dir / index_name
    try:
        lines = []
        if index_file.exists():
            content = index_file.read_text(encoding='utf-8')
            for line in content.strip().split('\n'):
                if line and not line.startswith(cache_key + ':'):
                    lines.append(line)
        
        lines.append(f"{cache_key}:{filename}")
        index_file.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    except Exception as e:
        _logger.debug(f"[WebFetch] 更新缓存索引失败: {e}")


def _is_cache_expired(metadata: dict) -> bool:
    """检查缓存是否过期。"""
    expires_at = metadata.get('expires_at')
    if not expires_at:
        return True
    
    try:
        # 解析 ISO 格式时间
        if 'T' in expires_at:
            expires_time = datetime.fromisoformat(expires_at)
        else:
            expires_time = datetime.strptime(expires_at, '%Y-%m-%d %H:%M:%S')
        
        return datetime.now() > expires_time
    except Exception:
        return True


def _read_cached_content(cache_file: Path) -> tuple[str, dict] | None:
    """
    读取缓存文件内容。
    
    返回: (markdown_content, metadata) 或 None（如果读取失败）
    """
    try:
        content = cache_file.read_text(encoding='utf-8')
        metadata = _parse_cache_metadata(content)
        if not metadata:
            return None
        
        # 提取正文（跳过 front matter）
        match = re.search(r'^---\n.*?\n---\n', content, re.DOTALL)
        if match:
            markdown_content = content[match.end():]
        else:
            markdown_content = content
        
        return markdown_content, metadata
    except Exception as e:
        _logger.debug(f"[WebFetch] 读取缓存文件失败: {e}")
        return None


def _convert_html_to_markdown(html: str) -> str:
    """将 HTML 转换为 Markdown。"""
    try:
        import html2text  # type: ignore
        h = html2text.HTML2Text()
        h.ignore_links = False
        h.ignore_images = False
        h.ignore_tables = False
        h.body_width = 0  # 不自动换行
        return h.handle(html)
    except ImportError:
        # 兜底：简单的 HTML 清理
        _logger.debug("[WebFetch] html2text 未安装，使用简单转换")
        txt = html
        txt = re.sub(r'(?is)<script.*?>.*?</script>', '', txt)
        txt = re.sub(r'(?is)<style.*?>.*?</style>', '', txt)
        txt = re.sub(r'(?s)<[^>]+>', '\n', txt)
        txt = re.sub(r'\n{3,}', '\n\n', txt)
        return txt.strip()


def fetch_web_content(
    url: str,
    format: Literal["markdown", "text"] = "markdown",
    timeout: int = 30,
    workspace_root: str | None = None,
    use_cache: bool = True,
    force_refresh: bool = False,
) -> ToolResult:
    """
    获取网页内容（支持本地 Markdown 缓存）。
    
    Args:
        url: 目标 URL
        format: 返回格式（markdown/text）
        timeout: 请求超时时间（秒）
        workspace_root: 工作区根目录（用于缓存路径）
        use_cache: 是否使用缓存
        force_refresh: 是否强制刷新（忽略缓存）
    
    Returns:
        ToolResult 包含抓取的内容或错误信息
    """
    # 检查工具是否启用
    config = get_web_config()
    if not config.enabled:
        _logger.warning("[WebFetch] 网页抓取工具已被禁用")
        return ToolResult(False, error={"code": "E_TOOL_DISABLED", "message": "web tool is disabled"})

    _logger.debug(f"[WebFetch] 开始获取网页: url={url}, format={format}, timeout={timeout}, use_cache={use_cache}")
    
    # 验证 URL
    try:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            _logger.warning(f"[WebFetch] 无效的 URL 格式: {url}")
            return ToolResult(ok=False, error={"code": "E_INVALID_URL", "message": "invalid url format"})
        if parsed.scheme not in {"http", "https"}:
            return ToolResult(ok=False, error={"code": "E_INVALID_URL", "message": f"unsupported scheme: {parsed.scheme}"})
    except Exception as e:
        return ToolResult(ok=False, error={"code": "E_INVALID_URL", "message": str(e)})

    # 缓存相关：最终是否启用缓存由 config.cache_enabled 决定
    cache_key = _url_to_cache_key(url)
    cfg = config
    effective_use_cache = bool(use_cache) and bool(getattr(cfg, "cache_enabled", True))
    cache_dir = _get_cache_dir(workspace_root, cache_dir=str(getattr(cfg, "cache_dir", ".clude/markdown") or ".clude/markdown"))
    cached_file: Path | None = None
    from_cache = False
    
    # 1. 检查本地缓存（如果启用且非强制刷新）
    if effective_use_cache and not force_refresh:
        cached_file = _find_cache_file(cache_dir, cache_key, cfg=cfg)
        if cached_file:
            result = _read_cached_content(cached_file)
            if result:
                markdown_content, metadata = result
                if not _is_cache_expired(metadata):
                    _logger.info(f"[WebFetch] 命中缓存: {cached_file.name} (URL: {url})")
                    
                    # 根据请求的格式返回
                    content = markdown_content
                    if format == "text":
                        # 从 Markdown 转为纯文本（移除 Markdown 标记）
                        content = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', content)  # 链接
                        content = re.sub(r'[*_`#]+', '', content)  # 格式标记
                        content = re.sub(r'\n{3,}', '\n\n', content)
                    
                    # 应用长度限制
                    max_len = int(getattr(config, "max_content_length", 50000) or 50000)
                    truncated = False
                    if len(content) > max_len:
                        content = content[:max_len] + "\n\n[Content truncated due to length]"
                        truncated = True
                    
                    return ToolResult(
                        ok=True,
                        payload={
                            "url": url,
                            "format": format,
                            "content": content,
                            "content_length": len(content),
                            "truncated": truncated,
                            "from_cache": True,
                            "cache_file": str(cached_file),
                            "title": metadata.get("title", ""),
                            "fetched_at": metadata.get("fetched_at", ""),
                            "expires_at": metadata.get("expires_at", ""),
                        }
                    )
                else:
                    _logger.info(f"[WebFetch] 缓存已过期: {cached_file.name}")
    
    # 2. 网络抓取
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

    html_content = response.text
    
    # 3. 提取标题
    title = _extract_title_from_html(html_content)
    if not title:
        # 使用 URL 的最后部分作为标题
        title = parsed.path.split('/')[-1] or parsed.netloc
    
    # 4. 转换为 Markdown
    markdown_content = _convert_html_to_markdown(html_content)
    
    # 5. 保存到缓存
    if effective_use_cache:
        if _ensure_cache_dir(cache_dir):
            try:
                try:
                    max_fn_len = int(getattr(cfg, "cache_max_filename_length", 100) or 100)
                except Exception:
                    max_fn_len = 100
                safe_filename = _sanitize_filename(title, max_len=max_fn_len) + ".md"
                cache_file_path = cache_dir / safe_filename
                
                # 处理文件名冲突
                counter = 1
                try:
                    max_attempts = int(getattr(cfg, "cache_max_collision_attempts", 100) or 100)
                except Exception:
                    max_attempts = 100
                max_attempts = max(1, min(1000, max_attempts))
                while cache_file_path.exists():
                    # 检查是否是同一个 URL 的缓存
                    existing_result = _read_cached_content(cache_file_path)
                    if existing_result:
                        _, existing_meta = existing_result
                        if existing_meta.get('cache_key') == cache_key:
                            # 同一 URL，直接覆盖
                            break
                    
                    # 不同 URL，使用新文件名
                    safe_filename = f"{_sanitize_filename(title, max_len=max_fn_len)}_{counter}.md"
                    cache_file_path = cache_dir / safe_filename
                    counter += 1
                    if counter > max_attempts:
                        _logger.warning("[WebFetch] 文件名冲突过多，跳过缓存")
                        break
                
                if counter <= max_attempts:
                    cache_content = _build_cache_content(url, title, markdown_content, cache_key)
                    cache_file_path.write_text(cache_content, encoding='utf-8')
                    _update_cache_index(cache_dir, cache_key, safe_filename, cfg=cfg)
                    _logger.info(f"[WebFetch] 已缓存到: {cache_file_path}")
                    cached_file = cache_file_path
                    
            except Exception as e:
                _logger.warning(f"[WebFetch] 保存缓存失败: {e}")
    
    # 6. 根据请求的格式返回
    if format == "text":
        content = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', markdown_content)
        content = re.sub(r'[*_`#]+', '', content)
        content = re.sub(r'\n{3,}', '\n\n', content)
    else:
        content = markdown_content
    
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
        "from_cache": False,
        "title": title,
    }
    
    if cached_file:
        result_data["cache_file"] = str(cached_file)
        
        # 计算过期时间
        try:
            expiry_days = int(getattr(cfg, "cache_expiry_days", 7) or 7)
        except Exception:
            expiry_days = 7
        expiry_days = max(1, min(365, expiry_days))
        expires = datetime.now() + timedelta(days=expiry_days)
        result_data["expires_at"] = expires.isoformat()

    return ToolResult(ok=True, payload=result_data)


def clear_expired_cache(workspace_root: str | None = None) -> ToolResult:
    """
    清理过期的缓存文件。
    
    Args:
        workspace_root: 工作区根目录
    
    Returns:
        ToolResult 包含清理结果
    """
    cfg = get_web_config()
    cache_dir = _get_cache_dir(workspace_root, cache_dir=str(getattr(cfg, "cache_dir", ".clude/markdown") or ".clude/markdown"))
    if not cache_dir.exists():
        return ToolResult(ok=True, payload={"cleared": 0, "message": "缓存目录不存在"})
    
    cleared = 0
    errors = []
    
    try:
        for file in cache_dir.glob('*.md'):
            try:
                try:
                    scan_prefix = int(getattr(cfg, "cache_scan_prefix_bytes", 2000) or 2000)
                except Exception:
                    scan_prefix = 2000
                scan_prefix = max(256, min(20000, scan_prefix))
                content = file.read_text(encoding='utf-8')[:scan_prefix]
                metadata = _parse_cache_metadata(content)
                if metadata and _is_cache_expired(metadata):
                    file.unlink()
                    cleared += 1
                    _logger.debug(f"[WebFetch] 已删除过期缓存: {file.name}")
            except Exception as e:
                errors.append(f"{file.name}: {e}")
    except Exception as e:
        return ToolResult(ok=False, error={"code": "E_CACHE_CLEAR_FAILED", "message": str(e)})
    
    return ToolResult(
        ok=True,
        payload={
            "cleared": cleared,
            "errors": errors if errors else None,
            "message": f"已清理 {cleared} 个过期缓存文件"
        }
    )


def list_cache(workspace_root: str | None = None) -> ToolResult:
    """
    列出所有缓存文件。
    
    Args:
        workspace_root: 工作区根目录
    
    Returns:
        ToolResult 包含缓存列表
    """
    cfg = get_web_config()
    cache_dir = _get_cache_dir(workspace_root, cache_dir=str(getattr(cfg, "cache_dir", ".clude/markdown") or ".clude/markdown"))
    if not cache_dir.exists():
        return ToolResult(ok=True, payload={"files": [], "total": 0, "message": "缓存目录不存在"})
    
    files = []
    try:
        for file in sorted(cache_dir.glob('*.md'), key=lambda f: f.stat().st_mtime, reverse=True):
            try:
                try:
                    scan_prefix = int(getattr(cfg, "cache_scan_prefix_bytes", 2000) or 2000)
                except Exception:
                    scan_prefix = 2000
                scan_prefix = max(256, min(20000, scan_prefix))
                content = file.read_text(encoding='utf-8')[:scan_prefix]
                metadata = _parse_cache_metadata(content)
                if metadata:
                    files.append({
                        "filename": file.name,
                        "title": metadata.get("title", ""),
                        "url": metadata.get("url", ""),
                        "fetched_at": metadata.get("fetched_at", ""),
                        "expires_at": metadata.get("expires_at", ""),
                        "expired": _is_cache_expired(metadata),
                        "size_bytes": file.stat().st_size,
                    })
            except Exception:
                continue
    except Exception as e:
        return ToolResult(ok=False, error={"code": "E_CACHE_LIST_FAILED", "message": str(e)})
    
    return ToolResult(
        ok=True,
        payload={
            "files": files,
            "total": len(files),
            "cache_dir": str(cache_dir),
        }
    )
