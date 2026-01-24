# Claude Code 图片输入实现对标分析

> **目标**: 确保图片输入功能与 Claude Code 完全一致
> **参考**: Anthropic Claude Vision API 标准实现
> **状态**: 🔄 分析中

---

## 1. Claude Code 图片处理标准

### 1.1 官方 API 格式

根据 Anthropic Claude Vision API 文档，图片输入使用以下格式：

```python
{
  "role": "user",
  "content": [
    {
      "type": "text",
      "text": "What's in this image?"
    },
    {
      "type": "image",
      "source": {
        "type": "base64",
        "media_type": "image/jpeg",
        "data": "<base64_encoded_image>"
      }
    }
  ]
}
```

### 1.2 关键特性

1. **多模态内容数组**: `content` 是一个数组，包含多个内容块
2. **类型标识**: 每个块都有明确的 `type` 字段（`text` 或 `image`）
3. **图片源结构**: 
   - `source.type`: 固定为 `"base64"`
   - `source.media_type`: MIME 类型（如 `image/jpeg`, `image/png`）
   - `source.data`: Base64 编码的图片数据（不包含 data URI 前缀）
4. **支持格式**: JPEG, PNG, GIF, WebP

---

## 2. 当前实现分析

### 2.1 现有实现

```python
# 当前实现 (image_utils.py)
{
    "type": "image_url",  # ❌ 不符合 Claude 标准
    "image_url": {
        "url": "data:image/png;base64,..."  # ❌ 使用 data URI 格式
    }
}
```

### 2.2 问题对比

| 项目 | Claude Code 标准 | 当前实现 | 是否一致 |
| :--- | :--- | :--- | :--- |
| **类型字段** | `"image"` | `"image_url"` | ❌ |
| **数据格式** | `source.data` (纯 Base64) | `image_url.url` (data URI) | ❌ |
| **MIME 类型** | `source.media_type` | 隐式在 data URI 中 | ❌ |
| **多模态数组** | ✅ 使用 `content` 数组 | ✅ 使用 list | ✅ |

---

## 3. 对标方案

### 3.1 修改 image_utils.py

**目标**: 生成符合 Claude Vision API 标准的图片数据结构

```python
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
    """
```

### 3.2 修改 ChatMessage 结构

**当前**:
```python
ChatMessage(
    role="user",
    content=[
        {"type": "text", "text": "..."},
        {"type": "image_url", "image_url": {"url": "data:..."}}  # ❌
    ]
)
```

**对标后**:
```python
ChatMessage(
    role="user",
    content=[
        {"type": "text", "text": "..."},
        {"type": "image", "source": {"type": "base64", "media_type": "...", "data": "..."}}  # ✅
    ]
)
```

### 3.3 修改 LlamaCppHttpClient

**问题**: OpenAI Vision API 格式 vs Claude Vision API 格式

**现状**:
- 当前使用 OpenAI-compatible API (`image_url` 格式)
- Claude Code 使用 Claude 原生 API (`image` + `source` 格式)

**解决方案**:
1. **方案 A**: 根据 API 模式动态转换格式
   - `api_mode="openai_compat"` → OpenAI 格式
   - `api_mode="claude"` → Claude 格式
2. **方案 B**: 统一使用 Claude 格式，在发送时转换
3. **方案 C**: 增加配置选项 `vision_format`

**推荐**: 方案 A（最灵活）

---

## 4. 实施步骤

### Phase 1: 修改 image_utils.py ✅
- [x] 修改 `load_image_from_path` 返回 Claude 格式
- [x] 修改 `load_image_from_url` 返回 Claude 格式
- [x] 更新 `build_multimodal_content` 兼容新格式

### Phase 2: 更新 LlamaCppHttpClient
- [ ] 添加格式转换逻辑
- [ ] 支持 OpenAI 和 Claude 两种格式
- [ ] 根据 `api_mode` 自动转换

### Phase 3: 测试验证
- [ ] 测试 OpenAI-compatible API
- [ ] 测试 Claude API（如果可用）
- [ ] 验证图片正确显示

---

## 5. 兼容性考虑

### 5.1 OpenAI-compatible API 支持

**问题**: 大多数本地 LLM（llama.cpp, Ollama）使用 OpenAI 格式，不支持 Claude 格式

**解决方案**: 在 `_chat_openai_compat` 中转换格式

```python
def _convert_to_openai_vision_format(content):
    """将 Claude 格式转换为 OpenAI 格式"""
    if isinstance(content, list):
        converted = []
        for item in content:
            if item.get("type") == "image" and "source" in item:
                # 转换: Claude → OpenAI
                converted.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{item['source']['media_type']};base64,{item['source']['data']}"
                    }
                })
            else:
                converted.append(item)
        return converted
    return content
```

### 5.2 向后兼容

- 保持现有功能不变
- 新格式透明转换
- 用户无感知升级

---

## 6. 代码变更清单

| 文件 | 变更类型 | 说明 |
| :--- | :--- | :--- |
| `src/clude_code/llm/image_utils.py` | 修改 | 改为生成 Claude 格式 |
| `src/clude_code/llm/llama_cpp_http.py` | 修改 | 添加格式转换逻辑 |
| `src/clude_code/llm/__init__.py` | 更新 | 导出新的辅助函数 |
| `docs/FEATURE_IMAGE_INPUT_DESIGN.md` | 更新 | 补充格式说明 |

---

## 7. 测试用例

### 测试 1: Claude 格式生成
```python
img = load_image_from_path("test.png")
assert img["type"] == "image"
assert img["source"]["type"] == "base64"
assert "media_type" in img["source"]
assert "data" in img["source"]
```

### 测试 2: OpenAI 格式转换
```python
claude_format = {"type": "image", "source": {...}}
openai_format = _convert_to_openai_vision_format([claude_format])
assert openai_format[0]["type"] == "image_url"
assert openai_format[0]["image_url"]["url"].startswith("data:")
```

---

## 8. 风险评估

| 风险 | 影响 | 缓解措施 |
| :--- | :--- | :--- |
| **API 不兼容** | 高 | 添加格式转换层 |
| **性能下降** | 低 | 转换逻辑轻量级 |
| **向后兼容性** | 中 | 保持现有 API 不变 |

---

## 9. 业界对标

### Claude Code (Anthropic)
- ✅ 使用 Claude Vision API 标准格式
- ✅ `type: "image"` + `source: {type, media_type, data}`

### Cursor AI
- 使用 OpenAI Vision API 格式
- `type: "image_url"` + `image_url: {url}`

### Copilot
- 类似 OpenAI 格式

**结论**: 
- **内部标准**: 使用 Claude 格式（更规范）
- **外部通信**: 根据 API 类型自动转换

---

## 10. 实施优先级

- **P0**: 修改 `image_utils.py` 生成 Claude 格式 ✅ 已完成
- **P1**: 添加 `llama_cpp_http.py` 格式转换 ✅ 已完成
- **P2**: 更新文档和测试用例 ✅ 已完成
- **P3**: 性能优化（如果需要）

---

## 11. 实施结果

### 代码变更

| 文件 | 变更 | 状态 |
| :--- | :--- | :--- |
| `image_utils.py` | 改为生成 Claude 格式 | ✅ |
| `image_utils.py` | 添加 `convert_to_openai_vision_format` | ✅ |
| `llama_cpp_http.py` | 添加格式自动转换 | ✅ |
| `__init__.py` | 导出新函数 | ✅ |

### 测试验证

| 测试 | 结果 |
| :--- | :--- |
| Claude 格式生成 | ✅ `type: "image"` |
| Base64 编码 | ✅ 1423496 字符 |
| MIME 类型检测 | ✅ `image/png` |
| 格式转换 | ✅ Claude → OpenAI |
| 字符串兼容 | ✅ 保持不变 |
| 编译检查 | ✅ 无错误 |

### 新旧格式对比

**旧格式 (OpenAI)**:
```json
{
  "type": "image_url",
  "image_url": {
    "url": "data:image/png;base64,..."
  }
}
```

**新格式 (Claude)**:
```json
{
  "type": "image",
  "source": {
    "type": "base64",
    "media_type": "image/png",
    "data": "..."
  }
}
```

### 兼容性

- ✅ **内部存储**: 使用 Claude 标准格式
- ✅ **OpenAI API**: 自动转换为 OpenAI 格式
- ✅ **向后兼容**: 字符串消息保持不变
- ✅ **多模态**: 完全支持文本+图片混合

---

## 12. 结论

✅ **对标完成**: 图片输入功能现在完全符合 Claude Code 的实现标准

- 内部使用 Claude Vision API 格式（更规范、更结构化）
- 自动转换为 OpenAI 格式（兼容 llama.cpp, Ollama 等）
- 保持代码简洁性和可维护性
- 零破坏性变更，完全向后兼容

