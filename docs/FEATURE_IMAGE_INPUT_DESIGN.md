# 图片输入功能实现思路

> **创建日期**: 2026-01-23  
> **功能状态**: 📋 设计中

---

## 1. 功能概述

支持用户在对话中输入图片，让 LLM 进行视觉理解和分析。

**使用场景**：
- 分析 UI 截图，生成代码
- 分析架构图/流程图，理解设计
- 分析报错截图，定位问题
- 分析图表数据，提取信息

---

## 2. 当前架构分析

### 2.1 现有消息结构
```python
# src/clude_code/llm/llama_cpp_http.py
@dataclass(frozen=True)
class ChatMessage:
    role: Role  # "system" | "user" | "assistant"
    content: str  # 纯文本
```

**问题**：只支持纯文本，无法携带图片数据。

### 2.2 OpenAI Vision API 格式
```json
{
  "role": "user",
  "content": [
    {"type": "text", "text": "这张图片是什么？"},
    {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}}
  ]
}
```

### 2.3 支持 Vision 的模型
| Provider | 模型 | Vision 支持 |
| :--- | :--- | :--- |
| OpenAI | GPT-4V, GPT-4o | ✅ |
| Anthropic | Claude 3 系列 | ✅ |
| Qwen | Qwen-VL, Qwen2-VL | ✅ |
| llama.cpp | LLaVA, MiniCPM-V | ✅ (需 mmproj) |
| Ollama | llava, bakllava | ✅ |

---

## 3. 实现方案

### 3.1 扩展消息结构

**方案 A：Union 类型（推荐）**
```python
from typing import Union, Literal

@dataclass
class TextContent:
    type: Literal["text"] = "text"
    text: str

@dataclass
class ImageContent:
    type: Literal["image_url"] = "image_url"
    image_url: dict  # {"url": "data:image/...;base64,..."}

ContentPart = Union[TextContent, ImageContent]

@dataclass
class ChatMessage:
    role: Role
    content: Union[str, list[ContentPart]]  # 兼容纯文本和多模态
```

**方案 B：简化版本**
```python
@dataclass
class ChatMessage:
    role: Role
    content: str  # 文本内容
    images: list[str] | None = None  # Base64 编码的图片列表
```

### 3.2 图片处理模块

**新增文件**: `src/clude_code/llm/image_utils.py`

```python
import base64
from pathlib import Path
from PIL import Image
import io

MAX_IMAGE_SIZE = (1024, 1024)  # 最大分辨率
MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 最大 5MB

def load_image_as_base64(path: str | Path) -> str:
    """加载图片并转为 Base64"""
    with open(path, "rb") as f:
        data = f.read()
    
    # 检查大小
    if len(data) > MAX_IMAGE_BYTES:
        # 压缩图片
        data = _compress_image(data)
    
    # 检测格式
    mime = _detect_mime_type(data)
    b64 = base64.b64encode(data).decode("utf-8")
    return f"data:{mime};base64,{b64}"

def _compress_image(data: bytes) -> bytes:
    """压缩图片到合适大小"""
    img = Image.open(io.BytesIO(data))
    img.thumbnail(MAX_IMAGE_SIZE, Image.Resampling.LANCZOS)
    
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()

def _detect_mime_type(data: bytes) -> str:
    """检测图片 MIME 类型"""
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return "image/png"
    elif data[:2] == b'\xff\xd8':
        return "image/jpeg"
    elif data[:6] in (b'GIF87a', b'GIF89a'):
        return "image/gif"
    elif data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return "image/webp"
    return "image/jpeg"  # 默认
```

### 3.3 修改 LLM 客户端

**文件**: `src/clude_code/llm/llama_cpp_http.py`

```python
def chat(self, messages: list[ChatMessage]) -> str:
    """发送消息并获取回复"""
    
    # 转换消息格式
    api_messages = []
    for msg in messages:
        if isinstance(msg.content, str):
            # 纯文本消息
            api_messages.append({"role": msg.role, "content": msg.content})
        else:
            # 多模态消息
            api_messages.append({"role": msg.role, "content": msg.content})
    
    # 发送请求
    ...
```

### 3.4 CLI 交互支持

**文件**: `src/clude_code/cli/chat_handler.py`

```python
def process_input(self, user_input: str) -> str:
    """处理用户输入"""
    
    # 检测图片路径
    # 支持格式：@image:path/to/image.png 或 拖拽文件
    images = []
    text_parts = []
    
    for part in user_input.split():
        if part.startswith("@image:"):
            path = part[7:]
            if Path(path).exists():
                images.append(load_image_as_base64(path))
            else:
                text_parts.append(part)
        else:
            text_parts.append(part)
    
    text = " ".join(text_parts)
    
    if images:
        return self._create_multimodal_message(text, images)
    return text
```

### 3.5 工具支持：analyze_image

**新增工具**: `src/clude_code/tooling/tools/analyze_image.py`

```python
def analyze_image(
    *,
    path: str,
    question: str = "请描述这张图片的内容",
) -> ToolResult:
    """
    分析图片内容（需要 Vision 模型支持）。
    
    Args:
        path: 图片路径（支持 png/jpg/gif/webp）
        question: 对图片的提问
    
    Returns:
        LLM 对图片的分析结果
    """
    ...
```

---

## 4. 实现步骤

### Phase 1: 基础设施（P0）✅ 已完成
- [x] 4.1.1 扩展 `ChatMessage` 数据结构支持多模态
- [x] 4.1.2 创建 `image_utils.py` 图片处理模块
- [x] 4.1.3 `LlamaCppHttpClient.chat()` 已兼容多模态消息

### Phase 2: CLI 集成（P1）待实现
- [ ] 4.2.1 CLI 支持 `@image:path` 语法输入图片
- [ ] 4.2.2 支持拖拽图片文件（Windows/macOS）
- [ ] 4.2.3 添加 `/image` 斜杠命令

### Phase 3: 工具集成（P2）✅ 已完成
- [x] 4.3.1 添加 `analyze_image` 工具
- [x] 4.3.2 工具返回图片数据（OpenAI Vision API 格式）

---

## 5. 代码变更清单

| 文件 | 变更类型 | 说明 |
| :--- | :--- | :--- |
| `src/clude_code/llm/llama_cpp_http.py` | 修改 | 扩展 ChatMessage 和 chat() |
| `src/clude_code/llm/image_utils.py` | 新增 | 图片加载、压缩、Base64 编码 |
| `src/clude_code/cli/chat_handler.py` | 修改 | 支持 @image 语法 |
| `src/clude_code/cli/slash_commands.py` | 修改 | 添加 /image 命令 |
| `src/clude_code/tooling/tools/analyze_image.py` | 新增 | analyze_image 工具 |
| `src/clude_code/orchestrator/agent_loop/tool_dispatch.py` | 修改 | 注册 analyze_image 工具 |

---

## 6. 依赖项

```
# requirements.txt 新增
Pillow>=10.0.0  # 图片处理
```

---

## 7. 使用示例

### 7.1 CLI 交互
```bash
# 方式 1：@image 语法
you: @image:screenshot.png 这个报错是什么原因？

# 方式 2：/image 命令
you: /image screenshot.png
you: 分析这个架构图

# 方式 3：拖拽（待实现）
# 直接拖拽图片到终端
```

### 7.2 工具调用
```json
{"tool": "analyze_image", "args": {"path": "ui_design.png", "question": "这个 UI 有什么问题？"}}
```

---

## 8. 注意事项

1. **模型兼容性**：检测当前模型是否支持 Vision，不支持时给出提示
2. **Token 消耗**：图片会显著增加 token 消耗，需要在上下文管理中考虑
3. **隐私安全**：图片可能包含敏感信息，需要在本地处理而非上传
4. **大小限制**：自动压缩大图片，避免超出 API 限制


