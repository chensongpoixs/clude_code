"""
图片处理工具（Image Utilities）

支持从本地路径或 URL 加载图片，转为 Base64 格式用于 Vision API。
"""
from __future__ import annotations

import base64
import re
from pathlib import Path
from typing import Any
import logging

logger = logging.getLogger(__name__)

# 支持的图片格式
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}

# 图片 URL 正则
IMAGE_URL_PATTERN = re.compile(
    r"https?://[^\s]+\.(?:png|jpg|jpeg|gif|webp|bmp)(?:\?[^\s]*)?",
    re.IGNORECASE
)

# 本地图片路径正则（支持 Windows 和 Unix 路径）
IMAGE_PATH_PATTERN = re.compile(
    r"(?:[A-Za-z]:[\\\/]|[\\\/]|\.{0,2}[\\\/])?[\w\-. \\\/]+\.(?:png|jpg|jpeg|gif|webp|bmp)",
    re.IGNORECASE
)


def detect_mime_type(data: bytes) -> str:
    """检测图片 MIME 类型"""
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return "image/png"
    elif data[:2] == b'\xff\xd8':
        return "image/jpeg"
    elif data[:6] in (b'GIF87a', b'GIF89a'):
        return "image/gif"
    elif data[:4] == b'RIFF' and len(data) > 12 and data[8:12] == b'WEBP':
        return "image/webp"
    elif data[:2] == b'BM':
        return "image/bmp"
    return "image/jpeg"  # 默认


def load_image_from_path(path: str | Path) -> dict[str, Any] | None:
    """
    从本地路径加载图片，返回 Claude Vision API 格式。
    
    Returns:
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": "<base64_string>"
            }
        }
        或 None（加载失败）
    """
    try:
        p = Path(path)
        if not p.exists():
            logger.warning(f"[ImageUtils] 图片不存在: {path}")
            return None
        
        if not p.is_file():
            logger.warning(f"[ImageUtils] 不是文件: {path}")
            return None
        
        if p.suffix.lower() not in IMAGE_EXTENSIONS:
            logger.warning(f"[ImageUtils] 不支持的图片格式: {p.suffix}")
            return None
        
        data = p.read_bytes()
        mime = detect_mime_type(data)
        b64 = base64.b64encode(data).decode("utf-8")
        
        logger.info(f"[ImageUtils] 加载图片成功: {path} ({len(data)} bytes, {mime})")
        
        return {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": mime,
                "data": b64
            }
        }
    except Exception as e:
        logger.error(f"[ImageUtils] 加载图片失败: {path}, 错误: {e}")
        return None


def load_image_from_url(url: str) -> dict[str, Any] | None:
    """
    从 URL 加载图片，返回 Claude Vision API 格式。
    
    注意：部分 API（如 OpenAI）直接支持 URL，无需下载。
    本地 LLM（如 llama.cpp）可能需要下载后转 Base64。
    
    Returns:
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": "<base64_string>"
            }
        }
    """
    try:
        import httpx
        
        # 尝试下载图片
        with httpx.Client(timeout=30) as client:
            resp = client.get(url)
            resp.raise_for_status()
            data = resp.content
        
        mime = detect_mime_type(data)
        b64 = base64.b64encode(data).decode("utf-8")
        
        logger.info(f"[ImageUtils] 下载图片成功: {url} ({len(data)} bytes, {mime})")
        
        return {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": mime,
                "data": b64
            }
        }
    except ImportError:
        # 如果没有 httpx，直接返回 URL（让 API 自己处理）
        logger.info(f"[ImageUtils] 直接使用 URL: {url}")
        return {
            "type": "image",
            "source": {
                "type": "url",
                "url": url
            }
        }
    except Exception as e:
        logger.error(f"[ImageUtils] 下载图片失败: {url}, 错误: {e}")
        return None


def extract_images_from_text(text: str) -> tuple[str, list[dict[str, Any]]]:
    """
    从文本中提取图片路径/URL，返回清理后的文本和图片列表。
    
    支持格式：
    - 本地路径：./image.png, D:/images/test.jpg, /home/user/pic.png
    - URL：https://example.com/image.png
    
    Returns:
        (clean_text, images)
    """
    images: list[dict[str, Any]] = []
    clean_parts: list[str] = []
    
    # 先处理 URL
    url_matches = IMAGE_URL_PATTERN.findall(text)
    for url in url_matches:
        img = load_image_from_url(url)
        if img:
            images.append(img)
        text = text.replace(url, "")
    
    # 再处理本地路径
    path_matches = IMAGE_PATH_PATTERN.findall(text)
    for path in path_matches:
        # 验证是否真的是图片文件
        p = Path(path.strip())
        if p.exists() and p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS:
            img = load_image_from_path(path.strip())
            if img:
                images.append(img)
            text = text.replace(path, "")
    
    # 清理多余空格
    clean_text = " ".join(text.split()).strip()
    
    return clean_text, images


def convert_to_openai_vision_format(content: str | list[dict[str, Any]]) -> str | list[dict[str, Any]]:
    """
    将 Claude Vision API 格式转换为 OpenAI Vision API 格式。
    
    用于兼容 OpenAI-compatible API（如 llama.cpp, Ollama）。
    
    Args:
        content: ChatMessage.content (可以是字符串或多模态列表)
    
    Returns:
        转换后的 content
    
    Examples:
        # 输入 (Claude 格式):
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": "..."
            }
        }
        
        # 输出 (OpenAI 格式):
        {
            "type": "image_url",
            "image_url": {
                "url": "data:image/jpeg;base64,..."
            }
        }
    """
    # 如果是字符串，直接返回
    if isinstance(content, str):
        return content
    
    # 如果不是列表，返回原值
    if not isinstance(content, list):
        return content
    
    # 转换多模态内容
    converted = []
    for item in content:
        if not isinstance(item, dict):
            converted.append(item)
            continue
        
        # Claude 格式 → OpenAI 格式
        if item.get("type") == "image" and "source" in item:
            source = item["source"]
            
            if source.get("type") == "base64":
                # Base64 图片
                media_type = source.get("media_type", "image/jpeg")
                data = source.get("data", "")
                converted.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{media_type};base64,{data}"
                    }
                })
            elif source.get("type") == "url":
                # URL 图片
                converted.append({
                    "type": "image_url",
                    "image_url": {
                        "url": source.get("url", "")
                    }
                })
            else:
                # 未知 source 类型，保持原样
                converted.append(item)
        else:
            # 非图片内容，保持原样
            converted.append(item)
    
    return converted


def build_multimodal_content(text: str, images: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    构建多模态消息内容（OpenAI Vision API 格式）。
    
    Returns:
        [{"type": "text", "text": "..."}, {"type": "image_url", ...}, ...]
    """
    content: list[dict[str, Any]] = []
    
    # 文本部分
    if text:
        content.append({"type": "text", "text": text})
    
    # 图片部分
    content.extend(images)
    
    return content

