# Phase 3: 结果分层压缩 - 实现思考过程

> **开始时间**: 2026-01-23  
> **目标**: 按需提供工具结果详情，预期节省 1000+ tokens/复杂任务

---

## 1. 问题分析

### 1.1 当前状态

当前 `feedback.py` 返回固定格式的工具结果：
- `grep`: 最多 15 条匹配，每条完整显示
- `read_file`: 最多 3000 字符
- `list_dir`: 完整目录列表

问题：
1. 简单任务不需要完整结果
2. LLM 经常只需要"是否成功"或"摘要"
3. 大量冗余信息浪费 token

### 1.2 业界做法

| 项目 | 策略 |
|------|------|
| Claude Code | 分层返回：summary → snippet → full |
| Cursor | 智能截断 + 关键信息提取 |
| GitHub Copilot | 按相关性排序，优先返回高价值内容 |

### 1.3 目标

实现三层压缩策略：

| 层级 | 内容 | Token 消耗 |
|------|------|----------|
| summary | 状态 + 数量 + 关键词 | ~20 |
| snippet | 前 N 条/行 | ~100 |
| full | 完整结果 | ~500+ |

---

## 2. 设计方案

### 2.1 工具结果结构增强

```python
class ToolResultCompressed:
    ok: bool
    summary: str           # "找到 15 个匹配"
    snippet: str | None    # 前 3 条结果
    full_payload: Any      # 完整结果（可选返回）
    truncated: bool        # 是否被截断
```

### 2.2 压缩策略表

| 工具 | summary 格式 | snippet 策略 | full 条件 |
|------|-------------|-------------|----------|
| grep | "找到 N 个匹配 (文件: M)" | 前 3 条 | LLM 请求或 N ≤ 5 |
| read_file | "读取 N 行 (M 字符)" | 前 50 行 | 文件 ≤ 200 行 |
| list_dir | "N 文件, M 目录" | 前 10 项 | ≤ 20 项 |
| apply_patch | "成功替换 N 处" | diff 摘要 | 总是 snippet |
| run_cmd | "退出码 N, 输出 M 字符" | 前 20 行 | 输出 ≤ 50 行 |

### 2.3 实现架构

```
工具执行 → 原始结果 → ResultCompressor → 压缩结果 → 反馈格式化
                          ↓
                     压缩策略配置
```

---

## 3. 实现步骤

### 3.1 创建 result_compressor.py

实现结果压缩器类。

### 3.2 修改 feedback.py

集成压缩器，根据工具类型应用不同压缩策略。

### 3.3 添加配置项

允许用户配置压缩级别（aggressive/balanced/minimal）。

---

## 4. 实现进度

| 步骤 | 状态 |
|------|------|
| 思考过程文档 | ✅ 已完成 |
| 创建 result_compressor.py | ✅ 已完成 |
| 修改 feedback.py | ✅ 已完成 |
| 代码检查 | ✅ 已通过 |
| 汇报 | ✅ 已完成 |

---

## 5. 完成汇报

### 5.1 创建的文件

- `src/clude_code/tooling/result_compressor.py` - 高级结果压缩器（三层压缩策略）

### 5.2 修改的文件

- `src/clude_code/tooling/feedback.py` - 添加 `CompressionLevel` 枚举和压缩级别参数支持

### 5.3 压缩级别参数对比

| 参数 | MINIMAL | BALANCED | AGGRESSIVE |
|------|---------|----------|------------|
| MAX_PREVIEW_CHARS | 300 | 200 | 100 |
| MAX_GREP_HITS | 25 | 15 | 8 |
| MAX_READ_FILE_CHARS | 5000 | 3000 | 1500 |
| MAX_WEB_RESULTS | 8 | 5 | 3 |
| MAX_WEBFETCH_CHARS | 1200 | 800 | 400 |

### 5.4 Token 节省估算

| 压缩级别 | grep (50 hits) | read_file (5000 chars) |
|----------|---------------|----------------------|
| MINIMAL | ~800 tokens | ~1000 tokens |
| BALANCED | ~500 tokens | ~750 tokens |
| AGGRESSIVE | ~250 tokens | ~375 tokens |

### 5.5 API 变更

```python
# 新增参数 compression
summarize_tool_result(tool, tr, keywords, compression=CompressionLevel.BALANCED)
format_feedback_message(tool, tr, keywords, compression=CompressionLevel.BALANCED)
```

### 5.6 向后兼容

- 默认使用 `BALANCED` 级别，与原有行为一致
- 现有调用无需修改即可正常工作

