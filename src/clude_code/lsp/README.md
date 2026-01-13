# LSP (Language Server Protocol) 集成模块

> 模块路径: `src/clude_code/lsp/`
> 阶段: Phase 4 - 生态与扩展

---

## 概述

本模块提供 Language Server Protocol 客户端能力，支持精确的符号跳转、引用分析、代码补全等功能。

## 业界对比

| 项目 | LSP 支持 | 实现方式 | 优点 | 缺点 |
|:---|:---|:---|:---|:---|
| **Cursor** | ✅ 完整 | 内置多语言 | 开箱即用 | 闭源 |
| **Continue.dev** | ✅ 部分 | IDE 代理 | 低开发成本 | 依赖 IDE |
| **Aider** | ❌ | ctags | 简单 | 精度低 |
| **本项目** | ✅ | 通用客户端 | 跨平台、可扩展 | 需安装 LSP 服务器 |

## 架构

```
┌─────────────────────────────────────────────────────────┐
│                    LSPManager                           │
│  ┌───────────────────────────────────────────────────┐  │
│  │ 自动语言检测 → 启动/管理对应 LSP 服务器           │  │
│  └───────────────────────────────────────────────────┘  │
│                          │                              │
│          ┌───────────────┼───────────────┐              │
│          ▼               ▼               ▼              │
│   ┌──────────┐    ┌──────────┐    ┌──────────┐         │
│   │ pylsp    │    │ gopls    │    │ tsserver │ ...     │
│   │ (Python) │    │ (Go)     │    │ (TS/JS)  │         │
│   └──────────┘    └──────────┘    └──────────┘         │
└─────────────────────────────────────────────────────────┘
```

## 支持的语言服务器

| 语言 | 服务器 | 安装命令 |
|:---|:---|:---|
| Python | pylsp | `pip install python-lsp-server` |
| TypeScript/JS | typescript-language-server | `npm i -g typescript-language-server typescript` |
| Go | gopls | `go install golang.org/x/tools/gopls@latest` |
| Rust | rust-analyzer | `rustup component add rust-analyzer` |
| C/C++ | clangd | 系统包管理器安装 |

## 核心能力

### 1. 跳转到定义

```python
client = LSPClient(workspace_root, "python")
client.start()
locations = client.go_to_definition("src/main.py", line=10, character=5)
# [LSPLocation(uri="file:///...", start_line=25, ...)]
```

### 2. 查找引用

```python
refs = client.find_references("src/utils.py", line=5, character=10)
# 返回所有使用该符号的位置
```

### 3. 获取文档符号

```python
symbols = client.get_document_symbols("src/main.py")
# [LSPSymbol(name="main", kind=12, ...), ...]
```

### 4. 搜索工作区符号

```python
results = manager.search_symbols("Config")
# 在所有已启动的语言服务器中搜索
```

## 集成方式

### 作为扩展工具

```python
from clude_code.tooling.extended_tools import ExtendedTools

tools = ExtendedTools(workspace_root)
result = tools.lsp_go_to_definition("src/main.py", 10, 5)
```

### 工具调用格式

```json
{"tool": "lsp_go_to_definition", "args": {"path": "src/main.py", "line": 10, "character": 5}}
```

## 健壮性设计

- **超时保护**: 所有 LSP 请求有超时限制（默认 30s）
- **服务器崩溃恢复**: 检测到服务器死亡后自动重启
- **异步消息处理**: 后台线程读取消息，避免阻塞主线程
- **优雅降级**: LSP 服务器不可用时返回空结果而非报错

