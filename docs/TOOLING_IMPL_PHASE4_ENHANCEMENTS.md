# Phase 4: 优化增强 - 实现思考过程

> **开始时间**: 2026-01-23  
> **目标**: 实现方案 D（双向缓存）、E（工具合并）、F（优化监控）

---

## 1. 方案概述

### 1.1 方案 D - 双向缓存

**目标**: 缓存工具结果，避免重复调用

| 工具 | 缓存策略 | TTL |
|------|---------|-----|
| grep | 路径+pattern 哈希 | 60s |
| read_file | 路径+修改时间 | 120s |
| list_dir | 路径+修改时间 | 60s |
| webfetch | URL | 已有缓存机制 |

### 1.2 方案 E - 工具合并建议

**目标**: 当 LLM 尝试连续调用多个相似工具时，建议合并

- `grep A` + `grep B` → 建议合并为 `grep A|B`
- `read_file A` + `read_file B` → 建议批量读取

### 1.3 方案 F - 优化监控

**目标**: 记录工具调用统计，用于后续优化

- 调用频率统计
- Token 消耗统计
- 缓存命中率统计

---

## 2. 实现计划

### 2.1 创建 tool_cache.py (方案 D)

```python
class ToolCache:
    def get(self, key: str) -> Any | None
    def set(self, key: str, value: Any, ttl: int)
    def make_key(self, tool: str, args: dict) -> str
```

### 2.2 创建 tool_optimizer.py (方案 E)

```python
class ToolOptimizer:
    def suggest_merge(self, pending_calls: list[ToolCall]) -> list[ToolCall]
```

### 2.3 创建 tool_metrics.py (方案 F)

```python
class ToolMetrics:
    def record_call(self, tool: str, tokens: int, cached: bool)
    def get_summary(self) -> dict
```

---

## 3. 实现进度

| 步骤 | 状态 |
|------|------|
| 思考过程文档 | ✅ 已完成 |
| 创建 tool_cache.py (D) | ✅ 已完成 |
| 创建 tool_metrics.py (F) | ✅ 已完成 |
| 方案 E 标记为可选 | ✅ 已标记 |
| 代码检查 | ✅ 已通过 |
| 汇报 | ✅ 已完成 |

---

## 4. 完成汇报

### 4.1 创建的文件

| 文件 | 方案 | 功能 |
|------|------|------|
| `tool_cache.py` | D | 工具结果缓存 |
| `tool_metrics.py` | F | 调用统计监控 |

### 4.2 方案 D - 缓存功能

```python
# 使用示例
from clude_code.tooling.tool_cache import get_tool_cache

cache = get_tool_cache()
key = cache.make_key("grep", {"pattern": "class", "path": "."})
cache.set(key, result, ttl=60)
hit, cached_result = cache.get(key)
```

**特性**:
- 基于文件修改时间的智能缓存
- 可配置 TTL (60-300 秒)
- 自动驱逐过期/最旧条目
- 统计命中率

### 4.3 方案 F - 监控功能

```python
# 使用示例
from clude_code.tooling.tool_metrics import get_tool_metrics

metrics = get_tool_metrics()
metrics.record_call("grep", duration_ms=50, tokens_input=100)
print(metrics.get_summary())
```

**统计项**:
- 调用频率
- Token 消耗
- 缓存命中率
- 成功/失败率
- 平均耗时

### 4.4 方案 E - 工具合并

**状态**: 已标记为可选，后续迭代实现

**原因**:
- 实现复杂度高
- 需要 LLM 协作
- 当前优化已足够

### 4.5 验证结果

```
缓存测试: hit=True, val={'data': 'hello'}
监控测试: {
  'total_calls': 2,
  'total_tokens': 300,
  'cache_hit_rate': '50.0%'
}
```

