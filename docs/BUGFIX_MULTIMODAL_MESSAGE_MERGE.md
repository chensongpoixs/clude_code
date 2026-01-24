# Bug Fix: 多模态消息合并错误

> **问题**: TypeError: can only concatenate list (not "str") to list
> **影响**: 图片输入功能无法正常工作
> **状态**: ✅ 已修复

---

## 问题描述

当用户输入包含图片时（如 `@image:path` 语法），消息内容变为多模态格式（list），但 LLM IO 模块的消息规范化逻辑仍然假设所有消息都是字符串格式，导致类型不匹配错误。

**错误堆栈**:
```
TypeError: can only concatenate list (not "str") to list
  File "src/clude_code/orchestrator/agent_loop/llm_io.py", line 61, in normalize_messages_for_llama
    content=normalized[-1].content + "\n\n" + msg.content
```

---

## 根本原因

1. **ChatMessage.content 类型变化**: 引入多模态支持后，`content` 可以是 `str` 或 `list`
2. **消息规范化逻辑过时**: `normalize_messages_for_llama` 函数假设所有内容都是字符串
3. **连续角色合并失败**: 当合并连续的 user 消息时，一条是多模态，一条是字符串，导致类型错误

---

## 解决方案

### 修改文件: `src/clude_code/orchestrator/agent_loop/llm_io.py`

**修改内容**:
1. 添加 `_merge_message_content` 辅助函数，支持以下合并场景：
   - `str` + `str` → `str`
   - `list` + `str` → `list`（追加文本部分）
   - `str` + `list` → `list`（转换为多模态格式）
   - `list` + `list` → `list`（合并多模态内容）

2. 修改消息规范化逻辑，使用新的合并函数替代简单的字符串连接

---

## 代码变更

```python
def _merge_message_content(existing_content, new_content):
    """
    合并消息内容，支持字符串和多模态内容。
    """
    if isinstance(existing_content, str) and isinstance(new_content, str):
        # 两个都是字符串
        return existing_content + "\n\n" + new_content
    elif isinstance(existing_content, list) and isinstance(new_content, str):
        # existing 是多模态，new 是字符串 - 追加文本
        merged = existing_content.copy()
        if merged and isinstance(merged[-1], dict) and merged[-1].get("type") == "text":
            # 合并到最后一个文本部分
            merged[-1]["text"] += "\n\n" + new_content
        else:
            # 添加新的文本部分
            merged.append({"type": "text", "text": new_content})
        return merged
    elif isinstance(existing_content, str) and isinstance(new_content, list):
        # existing 是字符串，new 是多模态 - 转换为多模态格式
        merged = [{"type": "text", "text": existing_content}]
        merged.extend(new_content)
        return merged
    elif isinstance(existing_content, list) and isinstance(new_content, list):
        # 两个都是多模态 - 合并
        merged = existing_content.copy()
        merged.extend(new_content)
        return merged
    else:
        # 其他情况，直接使用新内容
        return new_content
```

---

## 测试验证

### 测试用例
1. **字符串 + 字符串**: `Hello` + `World` → `"Hello\n\nWorld"`
2. **多模态 + 字符串**: `[text, image]` + `text` → `[text, image, text]`
3. **字符串 + 多模态**: `text` + `[text, image]` → `[text, text, image]`
4. **多模态 + 多模态**: `[text1, image]` + `[text2]` → `[text1, image, text2]`

### 编译检查
- ✅ Python 语法正确
- ✅ 类型兼容性验证通过
- ✅ 导入测试通过

---

## 影响范围

- **修复功能**: 图片输入功能现在可以正常工作
- **兼容性**: 保持对纯文本消息的完全兼容
- **性能**: 无显著性能影响

---

## 预防措施

1. **类型检查**: 在消息处理中添加运行时类型检查
2. **测试覆盖**: 为多模态消息添加单元测试
3. **文档更新**: 更新消息格式说明文档

---

## 相关文件

- `src/clude_code/orchestrator/agent_loop/llm_io.py` (修改)
- `src/clude_code/llm/llama_cpp_http.py` (ChatMessage 定义)
- `src/clude_code/llm/image_utils.py` (图片处理)
