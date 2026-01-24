# 问题分析：图片输入导致规划失败

> **问题**: LLM 在规划阶段返回工具调用而非 Plan JSON
> **影响**: 无法生成执行计划，流程中断
> **状态**: 🔄 分析中

---

## 1. 问题现象

### 1.1 错误信息
```
✗ 计划解析失败 (尝试 1/2): 无法从模型输出中解析 Plan JSON
ValueError: 2 validation errors for Plan
  - title: Field required
  - steps: Field required
```

### 1.2 LLM 实际输出
```
一、思路分析
- 当前任务：分析提供的设计图...

二、工具调用
{"tool":"analyze_image","args":{"path":"screenshot.png",...}}
```

**问题**: LLM 输出了工具调用，而不是 Plan JSON

---

## 2. 根本原因分析

### 2.1 期望 vs 实际

| 维度 | 期望（规划阶段） | 实际（LLM 输出） |
| :--- | :--- | :--- |
| **输出格式** | Plan JSON | 工具调用 JSON |
| **必需字段** | `type`, `title`, `steps` | `tool`, `args` |
| **阶段理解** | 生成步骤计划 | 直接执行工具 |

### 2.2 原因推断

1. **Prompt 混淆**: 规划 prompt 可能没有明确禁止工具调用
2. **图片影响**: 图片内容让 LLM 认为应该直接分析，跳过规划
3. **上下文干扰**: 图片 + 用户输入让 LLM 误判当前阶段

---

## 3. 详细分析

### 3.1 消息上下文
```
messages = [
    ChatMessage(role="system", content="..."),
    ChatMessage(role="user", content=[
        {"type": "text", "text": "分析这个设计"},
        {"type": "image", "source": {...}}  # ← 图片数据
    ])
]
```

### 3.2 LLM 推理路径（推测）
1. 看到图片 → "需要分析图片内容"
2. 看到 `analyze_image` 工具 → "应该调用工具"
3. 输出工具调用 JSON → ❌ 跳过了规划阶段

---

## 4. 解决方案

### 方案 A: 增强规划 Prompt（推荐）

**修改**: `prompts/user/stage/planning.j2`

**增加明确指令**:
```jinja
# 重要约束
1. **本阶段只规划，不执行工具**
2. **严格输出 Plan JSON 格式**
3. **如果需要分析图片，在 steps 中规划 analyze_image 步骤**
4. **禁止直接输出工具调用 JSON**
```

### 方案 B: 预处理图片（备选）

**思路**: 在规划阶段不传递图片，只传递文本描述
- 规划阶段：只看文本 → 生成 Plan
- 执行阶段：传递图片 → 执行 analyze_image

**缺点**: 
- LLM 看不到图片，规划质量可能下降
- 需要修改 `agent_loop.py` 的消息构建逻辑

### 方案 C: 智能阶段判断（复杂）

**思路**: 检测 LLM 输出，如果是工具调用，自动转换为单步 Plan
- 检测到 `{"tool": "xxx"}` → 包装为 `{"type": "FullPlan", "steps": [...]}`

---

## 5. 推荐方案实施

### Phase 1: 增强规划 Prompt ✅

**修改文件**: `prompts/user/stage/planning.j2`

**添加约束**:
```jinja
## 严格输出要求

1. **禁止输出工具调用 JSON**
   - ❌ 错误: {"tool": "xxx", "args": {...}}
   - ✅ 正确: {"type": "FullPlan", "title": "...", "steps": [...]}

2. **如果需要使用工具，请在 steps 中规划**
   - 例如: {"id": "step_1", "description": "分析图片", "tools_expected": ["analyze_image"]}

3. **图片已在消息中，规划时可以参考图片内容，但不要直接调用工具**
```

### Phase 2: 添加输出验证

**修改文件**: `orchestrator/agent_loop/planning.py`

**在解析失败时，检测是否为工具调用误判**:
```python
if "tool" in assistant_plan and "args" in assistant_plan:
    # 检测到工具调用，自动转换为单步 Plan
    logger.warning("[Planning] 检测到工具调用输出，自动转换为 Plan")
    # 创建单步 Plan...
```

---

## 6. 预期效果

### 修改前
```
LLM 输出: {"tool": "analyze_image", ...}
解析结果: ❌ Plan 字段缺失
```

### 修改后
```
LLM 输出: {
  "type": "FullPlan",
  "title": "分析架构设计",
  "steps": [
    {
      "id": "step_1",
      "description": "使用 analyze_image 分析图片",
      "tools_expected": ["analyze_image"]
    }
  ]
}
解析结果: ✅ 成功
```

---

## 7. 风险评估

| 风险 | 影响 | 缓解措施 |
| :--- | :--- | :--- |
| **Prompt 冗长** | 低 | 保持简洁，只添加必要约束 |
| **LLM 不遵守** | 中 | 添加输出验证和自动修正 |
| **性能下降** | 低 | Prompt 增加不超过 100 tokens |

---

## 8. 实施步骤

1. ✅ 分析问题根因（已完成）
2. [ ] 修改 `planning.j2` 添加约束
3. [ ] 修改 `planning.py` 添加容错逻辑
4. [ ] 测试图片输入场景
5. [ ] 验证 Plan 生成正确性

---

## 9. 结论

**核心问题**: 
- LLM 在看到图片时，误判应该直接执行工具，跳过了规划阶段
- 规划 prompt 没有明确禁止工具调用输出

**解决方向**:
1. **增强 Prompt**: 明确规划阶段的输出格式和约束 ✅ 推荐
2. **添加容错**: 检测工具调用输出，自动转换为 Plan ✅ 推荐
3. **预处理图片**: 规划阶段不传图片（不推荐，降低规划质量）

**优先级**: P0（阻塞图片输入功能使用）

