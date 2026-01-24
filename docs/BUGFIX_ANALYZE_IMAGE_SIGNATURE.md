# Bug Fix: analyze_image 工具函数签名错误

> **问题**: TypeError: _h_analyze_image() takes 1 positional argument but 2 were given
> **根本原因**: 工具处理函数签名不符合调度器的调用约定
> **状态**: ✅ 已修复

---

## 1. 问题分析

### 错误信息
```
TypeError: _h_analyze_image() takes 1 positional argument but 2 were given
  File "tool_dispatch.py", line 1423, in dispatch_tool
    tr = spec.handler(loop, validated_args)
```

### 调用链路
1. LLM 输出工具调用：`{"tool": "analyze_image", "args": {"path": "...", "question": "..."}}`
2. `dispatch_tool` 解析并验证参数
3. 调用 `spec.handler(loop, validated_args)` - **传递 2 个位置参数**
4. `_h_analyze_image` 期望不同的签名格式 - **错误发生**

---

## 2. 根本原因

### 错误实现（修复前）
```python
def _h_analyze_image(
    loop: Any,
    *,  # ❌ 强制后续参数为关键字参数
    path: str,
    question: str = "请描述这张图片的内容",
) -> ToolResult:
```

### 问题
- `dispatch_tool` 调用方式：`handler(loop, validated_args)`
- `validated_args` 是一个**字典**，作为第 2 个**位置参数**传递
- 但 `*` 后的参数必须通过**关键字**传递
- 导致参数不匹配：期望 1 个位置参数（loop），但收到 2 个（loop + validated_args）

---

## 3. 解决方案

### 修复后的实现
```python
def _h_analyze_image(loop: Any, args: dict[str, Any]) -> ToolResult:
    """处理 analyze_image 工具调用。"""
    from clude_code.tooling.tools.analyze_image import analyze_image
    return analyze_image(
        path=args["path"],
        question=args.get("question", "请描述这张图片的内容")
    )
```

### 对比其他工具
查看现有工具实现（`_h_read_file`, `_h_grep`, `_h_write_file`），确认统一签名：
```python
def _h_xxx(loop: "AgentLoop", args: dict[str, Any]) -> ToolResult:
    # 接收 args 字典，解包参数传递给底层实现
```

---

## 4. 测试验证

### 测试场景
```python
# 模拟 dispatch_tool 的调用
loop = MockLoop()
validated_args = {'path': 'test.png', 'question': 'what is this?'}
result = _h_analyze_image(loop, validated_args)
```

### 测试结果
- ✅ 编译检查通过
- ✅ 函数调用成功
- ✅ 参数正确传递
- ✅ 图片正确加载
- ✅ 返回 ToolResult 对象

---

## 5. 修复效果

| 项目 | 修复前 | 修复后 |
| :--- | :--- | :--- |
| **调用状态** | ❌ TypeError | ✅ 正常 |
| **签名一致性** | ❌ 不一致 | ✅ 与其他工具一致 |
| **参数传递** | ❌ 失败 | ✅ 正确 |
| **图片加载** | ❌ 未执行 | ✅ 正常 |

---

## 6. 相关文件

- `src/clude_code/orchestrator/agent_loop/tool_dispatch.py` (修改)
- `src/clude_code/tooling/tools/analyze_image.py` (底层实现，无需修改)

---

## 7. 经验总结

### 问题根源
新增工具时未遵循项目现有的函数签名约定。

### 预防措施
1. **参考现有实现**：新增工具时先查看其他工具的实现模式
2. **统一签名约定**：所有工具处理函数使用 `(loop, args: dict) -> ToolResult`
3. **及早测试**：在集成前测试工具的完整调用链路

