# Phase 2: read_file 流式读取优化 - 实现思考过程

> **开始时间**: 2026-01-23  
> **目标**: 优化大文件读取，减少内存峰值，提高读取效率

---

## 1. 问题分析

### 1.1 当前实现问题

```python
# 当前代码 (src/clude_code/tooling/tools/read_file.py)
data = p.read_bytes()  # 问题：读取整个文件到内存

truncated = False
if len(data) > max_file_read_bytes:
    data = data[:max_file_read_bytes]  # 然后再截断
    truncated = True
```

**问题**:
1. 100MB 文件会占用 100MB 内存，即使只需要 2MB
2. 截断发生在读取之后，内存已经分配
3. 没有利用操作系统的文件缓冲机制

### 1.2 业界最佳实践

| 项目 | 策略 |
|------|------|
| Cursor | 分块读取 + mmap 大文件 |
| VS Code | 懒加载 + 流式读取 |
| Claude Code | 限制读取量 + 智能采样 |

### 1.3 目标

- 内存峰值 ≤ max_file_read_bytes * 1.2
- 大文件读取速度提升 50%+
- 支持智能采样（头部+尾部）

---

## 2. 设计方案

### 2.1 流式读取策略

```
文件大小判断
    │
    ├─ ≤ max_bytes → 直接读取
    │
    └─ > max_bytes → 分块读取
                      │
                      ├─ 指定 offset/limit → 定位读取
                      │
                      └─ 未指定 → 头部 + 尾部采样
```

### 2.2 核心函数设计

```python
def _read_file_smart(
    path: Path,
    max_bytes: int,
    offset: int | None = None,
    limit: int | None = None,
) -> tuple[str, int, bool, dict]:
    """
    智能文件读取。
    
    返回: (text, total_size, truncated, metadata)
    """
```

### 2.3 大文件智能采样

对于超大文件（> max_bytes），采用头尾采样策略：

```
文件总长: 100MB
max_bytes: 2MB

采样结果:
├─ 头部: 1.2MB (60%)
├─ 省略标记: "...[文件过大，已省略中间 97MB]..."
└─ 尾部: 0.8MB (40%)
```

---

## 3. 实现步骤

### 3.1 添加辅助函数

- `_get_file_size()`: 获取文件大小
- `_read_chunk()`: 分块读取
- `_read_with_sampling()`: 智能采样读取

### 3.2 重构主函数

- 修改 `read_file()` 使用新的流式读取逻辑
- 保持 API 兼容性

### 3.3 添加行号支持

- 可选返回带行号的内容（方便 LLM 定位）

---

## 4. 实现进度

| 步骤 | 状态 |
|------|------|
| 思考过程文档 | ✅ 已完成 |
| 实现流式读取函数 | ✅ 已完成 |
| 修改主函数 | ✅ 已完成 |
| 代码检查 | ✅ 已通过 |
| 汇报 | ✅ 已完成 |

---

## 5. 完成汇报

### 5.1 修改的文件

**`src/clude_code/tooling/tools/read_file.py`**

### 5.2 新增函数

```python
def _read_file_streaming(
    file_path: Path,
    max_bytes: int,
    offset: int | None = None,
    limit: int | None = None,
) -> tuple[str, int, bool, dict[str, Any]]:
```

### 5.3 优化特性

| 特性 | 描述 |
|------|------|
| 流式读取 | 大文件只读取需要的部分 |
| 头尾采样 | 超大文件采用 60%头部 + 40%尾部 |
| 行定位 | 支持 offset/limit 精确定位 |
| 元数据 | 返回 sampling_mode、skipped_bytes 等 |

### 5.4 内存优化效果

| 文件大小 | 原方案内存 | 优化后内存 | 节省 |
|---------|-----------|-----------|------|
| 1MB | ~1MB | ~1MB | 0% |
| 10MB | ~10MB | ~2MB | **80%** |
| 100MB | ~100MB | ~2MB | **98%** |

### 5.5 代码检查结果

- **编译**: ✅ 通过
- **Lint**: ✅ 无错误

