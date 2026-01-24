# Phase 1: 增强规划 Prompt 支持图片输入

> **目标**: 修改 planning.j2，明确规划阶段的输出要求
> **状态**: 🔄 进行中

---

## 1. 思考过程

### 1.1 问题分析
当用户输入包含图片时，LLM 容易混淆规划和执行的边界：
- **期望**: 生成包含 `analyze_image` 步骤的 Plan
- **实际**: 直接输出 `{"tool": "analyze_image", "args": {...}}`

### 1.2 设计思路

**核心原则**: 
1. 明确规划阶段只生成计划，不执行工具
2. 提供清晰的正确/错误示例
3. 针对图片场景提供特殊说明

**Prompt 增强策略**:
```
规划阶段 → 生成 Plan JSON
  ├─ 禁止输出工具调用 JSON
  ├─ 图片分析在 steps 中规划
  └─ 提供正确示例
```

---

## 2. 实现方案

### 2.1 在 planning.j2 中添加约束

**位置**: 紧接在 JSON 格式说明之后

**内容**:
```jinja
## 关键约束（Critical Constraints）

1. **禁止在规划阶段执行工具**
   - ❌ 错误输出: {"tool": "xxx", "args": {...}}
   - ✅ 正确输出: {"type": "FullPlan", "title": "...", "steps": [...]}

2. **图片分析场景**
   - 如果需要分析图片，在 steps 中规划 `analyze_image` 步骤
   - 不要直接调用工具，而是描述步骤目标

3. **步骤规划示例（包含图片）**
   ```json
   {
     "type": "FullPlan",
     "title": "分析设计图并提供建议",
     "steps": [
       {
         "id": "step_1",
         "description": "使用 analyze_image 分析图片内容，提取关键信息",
         "dependencies": [],
         "tools_expected": ["analyze_image"],
         "status": "pending"
       },
       {
         "id": "step_2",
         "description": "基于图片信息生成详细分析报告",
         "dependencies": ["step_1"],
         "tools_expected": ["display"],
         "status": "pending"
       }
     ]
   }
   ```
```

### 2.2 调整输出要求

**修改位置**: 最后的输出指令部分

**增强内容**:
```jinja
# 最终输出要求

1. 只输出一个 JSON 对象
2. JSON 的 `type` 字段必须是 `"FullPlan"`
3. 必须包含 `title` 和 `steps` 字段
4. 不要输出任何解释、思考过程或工具调用
```

---

## 3. 修改清单

| 位置 | 修改内容 | 目的 |
| :--- | :--- | :--- |
| JSON 格式说明后 | 添加"关键约束"部分 | 明确禁止工具调用 |
| 示例部分 | 添加图片场景示例 | 提供正确模板 |
| 输出要求 | 强化 JSON 格式要求 | 减少格式错误 |

---

## 4. 预期效果

### Before（修改前）
```
用户: 分析 @image:test.png 这个设计

LLM 输出:
{"tool": "analyze_image", "args": {"path": "test.png"}}

结果: ❌ 解析失败
```

### After（修改后）
```
用户: 分析 @image:test.png 这个设计

LLM 输出:
{
  "type": "FullPlan",
  "title": "分析设计图",
  "steps": [
    {
      "id": "step_1",
      "description": "使用 analyze_image 分析图片",
      "tools_expected": ["analyze_image"]
    }
  ]
}

结果: ✅ 解析成功
```

---

## 5. 风险评估

| 风险 | 概率 | 影响 | 缓解措施 |
| :--- | :--- | :--- | :--- |
| Prompt 过长 | 低 | 低 | 保持简洁，<200 tokens |
| LLM 不遵守 | 中 | 高 | Phase 2 添加容错逻辑 |
| 破坏现有功能 | 低 | 高 | 保留原有格式说明 |

---

## 6. 测试用例

### 测试 1: 纯文本输入
```
输入: "分析 device.cpp 的代码结构"
期望: 正常生成 Plan（不受影响）
```

### 测试 2: 图片输入
```
输入: "分析 @image:ui.png 这个界面设计"
期望: 生成包含 analyze_image 步骤的 Plan
```

### 测试 3: 多图片输入
```
输入: "对比 @image:v1.png @image:v2.png 两个版本"
期望: 生成包含多个 analyze_image 步骤的 Plan
```

---

## 7. 实施步骤

1. [ ] 读取 `planning.j2` 当前内容
2. [ ] 定位插入位置
3. [ ] 添加"关键约束"部分
4. [ ] 添加图片场景示例
5. [ ] 强化输出要求
6. [ ] 编译检查
7. [ ] 功能测试

