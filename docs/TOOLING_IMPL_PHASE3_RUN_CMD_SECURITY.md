# Phase 3: run_cmd 安全优化 - 实现思考过程

> **开始时间**: 2026-01-23  
> **目标**: 提高命令执行安全性，减少 shell 注入风险

---

## 1. 问题分析

### 1.1 当前实现问题

```python
# 当前代码 (src/clude_code/tooling/tools/run_cmd.py)
cp = subprocess.run(
    command,
    cwd=str(wd),
    shell=True,  # 问题：始终使用 shell 模式
    ...
)
```

**风险**:
- shell=True 允许 shell 元字符注入
- 例如 `ls; rm -rf /` 会执行两个命令
- 不安全的命令可能被意外执行

### 1.2 业界最佳实践

| 项目 | 策略 |
|------|------|
| Cursor | 命令白名单 + 参数解析 |
| Claude Code | 智能检测 shell 特性 |
| VS Code | 沙箱执行 + 权限控制 |

### 1.3 目标

- 优先使用 shell=False（更安全）
- 智能检测是否需要 shell
- 输出截断：头部 + 尾部（而非仅尾部）

---

## 2. 设计方案

### 2.1 命令解析策略

```
命令字符串
    │
    ├─ 包含 shell 特性 (|, >, <, &, ;, $, `) → shell=True
    │
    └─ 不包含 shell 特性 → shlex.split() → shell=False
```

### 2.2 Shell 特性检测

```python
SHELL_CHARS = {'|', '>', '<', '&', ';', '$(', '`', '*', '?'}
needs_shell = any(c in command for c in SHELL_CHARS)
```

### 2.3 输出截断优化

当前：仅保留尾部
优化后：头部 33% + 尾部 67%（保留开始和结束信息）

---

## 3. 实现步骤

### 3.1 添加命令解析函数

- `_parse_command()`: 智能解析命令，返回 (args, use_shell)

### 3.2 修改主函数

- 根据解析结果选择 shell=True/False
- 优化输出截断策略

### 3.3 添加命令日志

- 记录实际使用的 shell 模式

---

## 4. 实现进度

| 步骤 | 状态 |
|------|------|
| 思考过程文档 | ✅ 已完成 |
| 实现命令解析 | ✅ 已完成 |
| 修改主函数 | ✅ 已完成 |
| 代码检查 | ✅ 已通过 |
| 汇报 | ✅ 已完成 |

---

## 5. 完成汇报

### 5.1 修改的文件

**`src/clude_code/tooling/tools/run_cmd.py`**

### 5.2 新增函数

```python
def _parse_command(command: str) -> tuple[list[str] | str, bool]:
    """智能解析命令，决定是否需要 shell 模式。"""

def _truncate_output(output: str, max_bytes: int) -> tuple[str, bool]:
    """智能截断输出（头部 + 尾部）。"""
```

### 5.3 优化特性

| 特性 | 描述 |
|------|------|
| 智能 shell 检测 | 不含 shell 特性时使用 shell=False |
| Shell 特性集 | `|, >, <, &, ;, $, \`, *, ?, (, ), {, }, [, ], ~` |
| 头尾截断 | 33% 头部 + 67% 尾部（保留关键信息） |
| FileNotFoundError | 新增处理，返回 E_NOT_FOUND |

### 5.4 安全性提升

| 命令示例 | 原方案 | 优化后 |
|---------|--------|--------|
| `ls -la` | shell=True | **shell=False** |
| `python --version` | shell=True | **shell=False** |
| `cat file.txt` | shell=True | **shell=False** |
| `ls \| grep foo` | shell=True | shell=True |
| `echo $HOME` | shell=True | shell=True |

### 5.5 代码检查结果

- **编译**: ✅ 通过
- **Lint**: ✅ 无错误

