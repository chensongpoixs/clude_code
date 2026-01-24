"""LLM clients and adapters (llama.cpp HTTP, etc.)."""

from .llama_cpp_http import ChatMessage, LlamaCppHttpClient
from .image_utils import (
    load_image_from_path,
    load_image_from_url,
    extract_images_from_text,
    build_multimodal_content,
    convert_to_openai_vision_format,
)

__all__ = [
    "ChatMessage",
    "LlamaCppHttpClient",
    "load_image_from_path",
    "load_image_from_url",
    "extract_images_from_text",
    "build_multimodal_content",
    "convert_to_openai_vision_format",
]
