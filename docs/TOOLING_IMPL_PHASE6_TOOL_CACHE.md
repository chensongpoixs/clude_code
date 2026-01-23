# Phase 6: 工具结果缓存 - 实现思考过程

> **开始时间**: 2026-01-23  
> **目标**: 缓存工具结果，避免重复调用相同工具

---

## 1. 问题分析

### 1.1 当前问题

LLM 在多轮对话中可能重复调用相同的工具（相同参数）：

```
Turn 1: read_file("src/main.py")  # 首次调用
Turn 5: read_file("src/main.py")  # 重复调用（文件未变）
```

**问题**:
- 浪费 IO 资源
- 浪费 Token（重复输出相同内容）
- 响应延迟增加

### 1.2 业界最佳实践

| 项目 | 缓存策略 |
|------|---------|
| Cursor | 内存 LRU 缓存 + 文件哈希失效 |
| Claude Code | 会话级缓存 + TTL |
| Devin | 持久化缓存 + 智能失效 |

### 1.3 目标

- 会话级 LRU 缓存
- 只读工具（read_file, grep, list_dir 等）可缓存
- 写操作（write_file, apply_patch）后失效相关缓存

---

## 2. 设计方案

### 2.1 缓存键设计

```python
cache_key = (tool_name, frozenset(sorted(args.items())))
```

### 2.2 可缓存工具

| 工具 | 可缓存 | 说明 |
|------|--------|------|
| read_file | ✅ | 基于路径 + offset/limit |
| grep | ✅ | 基于 pattern + path |
| list_dir | ✅ | 基于 path |
| glob_file_search | ✅ | 基于 pattern + directory |
| search_semantic | ✅ | 基于 query |
| write_file | ❌ | 写操作 |
| apply_patch | ❌ | 写操作 |
| run_cmd | ❌ | 有副作用 |

### 2.3 失效策略

- 写操作后清除相关路径的缓存
- 会话结束时清空所有缓存

---

## 3. 实现进度

| 步骤 | 状态 |
|------|------|
| 思考过程文档 | ✅ 已完成 |
| 创建缓存模块 | ✅ 已完成 |
| 集成到调度器 | ✅ 已完成 |
| 代码检查 | ✅ 已通过 |
| 汇报 | ✅ 已完成 |

---

## 4. 完成汇报

### 4.1 新增文件

**`src/clude_code/tooling/tool_result_cache.py`**

### 4.2 核心类

```python
class ToolResultCache:
    """工具结果缓存（会话级 LRU）"""
    
    def get(self, tool: str, args: dict) -> dict | None
    def set(self, tool: str, args: dict, result: dict) -> None
    def invalidate_path(self, path: str) -> int
    def get_stats(self) -> dict
```

### 4.3 可缓存工具

| 工具 | 可缓存 |
|------|--------|
| read_file | ✅ |
| grep | ✅ |
| list_dir | ✅ |
| glob_file_search | ✅ |
| search_semantic | ✅ |
| websearch | ✅ |

### 4.4 特性

| 特性 | 描述 |
|------|------|
| LRU 淘汰 | 容量满时淘汰最旧条目 |
| TTL 过期 | 默认 300 秒过期 |
| 路径失效 | 写操作后失效相关缓存 |
| 统计报告 | 命中率、失效次数等 |

### 4.5 用法示例

```python
from clude_code.tooling.tool_result_cache import get_session_cache

cache = get_session_cache()

# 检查缓存
cached = cache.get("read_file", {"path": "main.py"})
if cached:
    return cached  # 直接返回，省去 IO

# 执行工具并缓存
result = read_file(path="main.py")
cache.set("read_file", {"path": "main.py"}, result)

# 写操作后失效
cache.invalidate_path("main.py")
```

### 4.6 代码检查结果

- **编译**: ✅ 通过
- **Lint**: ✅ 无错误

