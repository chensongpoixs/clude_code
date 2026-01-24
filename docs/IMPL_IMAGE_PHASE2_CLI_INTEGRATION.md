# Phase 2: CLI 图片输入集成

> **状态**: 🔄 进行中  
> **开始时间**: 2026-01-23

---

## 1. 目标

让用户在 CLI 中可以方便地输入图片，支持：
- `@image:path` 语法
- `/image` 斜杠命令

---

## 2. 思考过程

### 2.1 Phase 2.1: @image:path 语法

**用户输入示例**：
```
you: @image:screenshot.png 这个报错是什么原因？
you: 分析这个 @image:D:/work/ui.png 设计
```

**实现思路**：
1. 在 `chat_handler.py` 的输入处理中检测 `@image:` 前缀
2. 提取图片路径，调用 `load_image_from_path` 加载
3. 构建多模态消息发送给 LLM

**代码位置**：
- `src/clude_code/cli/chat_handler.py` - 主要修改
- `src/clude_code/cli/enhanced_chat_handler.py` - 同步修改

**关键修改**：
```python
def _process_user_input(self, user_input: str) -> tuple[str, list[dict]]:
    """处理用户输入，提取图片"""
    images = []
    clean_text = user_input
    
    # 匹配 @image:path 模式
    pattern = r'@image:([^\s]+)'
    matches = re.findall(pattern, user_input)
    
    for path in matches:
        img = load_image_from_path(path)
        if img:
            images.append(img)
            clean_text = clean_text.replace(f'@image:{path}', '')
    
    return clean_text.strip(), images
```

### 2.2 Phase 2.2: /image 斜杠命令

**用户输入示例**：
```
you: /image screenshot.png
you: /image https://example.com/img.png
```

**实现思路**：
1. 在 `slash_commands.py` 中添加 `/image` 命令
2. 命令加载图片并缓存，下次输入时自动附加
3. 显示图片已加载的提示

---

## 3. 实现步骤

### Phase 2.1 ✅ 已完成
- [x] 3.1.1 在 `chat_handler.py` 添加 `_extract_images_from_input` 方法
- [x] 3.1.2 修改 `AgentLoop.run_turn` 添加 `images` 参数
- [x] 3.1.3 修改 `_run_simple` 和 `_run_with_live` 传递图片
- [x] 3.1.4 编译检查 ✅ 通过

### Phase 2.2 ✅ 已完成
- [x] 3.2.1 在 `slash_commands.py` 添加 `/image` 命令
- [x] 3.2.2 实现图片缓存机制（通过 agent._pending_images）
- [x] 3.2.3 编译检查 ✅ 通过

---

## 4. 代码变更清单

| 文件 | 变更类型 | 说明 |
| :--- | :--- | :--- |
| `src/clude_code/cli/chat_handler.py` | 修改 | 添加 @image 语法支持 |
| `src/clude_code/cli/enhanced_chat_handler.py` | 修改 | 同步 @image 语法支持 |
| `src/clude_code/cli/slash_commands.py` | 修改 | 添加 /image 命令 |

