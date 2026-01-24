# P3：重构 `llama_cpp_http.py`（业界命名对齐 + 向后兼容）

> 依据：`docs/LLM_MODULE_NAMING_ANALYSIS.md` 的 P3 建议（`llama_cpp_http.py` 命名混合厂商与功能，可选重构）。

## 目标

在 **不破坏现有 import** 的前提下，把该模块的“通用 HTTP 客户端”职责以更业界化的命名承载：

- **新增** `src/clude_code/llm/http_client.py`：承载核心实现（`ChatMessage`、`LlamaCppHttpClient`）
- **保留** `src/clude_code/llm/llama_cpp_http.py`：改为兼容层（re-export），便于渐进迁移

## 1. 现状理解（模块功能）

### 1.1 `llama_cpp_http.py` 当前职责

该文件承担两类核心能力：

- **消息模型**：`ChatMessage`
  - `role`: `system/user/assistant`
  - `content`: `str` 或多模态 `list[dict]`
- **通用 OpenAI-compatible HTTP 客户端**：`LlamaCppHttpClient`
  - `openai_compat`: `POST {base_url}/v1/chat/completions`
  - `completion`: `POST {base_url}/completion`（llama.cpp 原生）
  - `GET {base_url}/v1/models` 发现模型
  - 多模态：Claude Vision → OpenAI Vision（通过 `image_utils.convert_to_openai_vision_format`）

### 1.2 影响面（引用分布）

`ChatMessage` / `LlamaCppHttpClient` 被大量模块引用：

- `src/clude_code/orchestrator/**`（消息归一化、执行、规划、react）
- `src/clude_code/cli/**`（doctor、utils、session_store）
- `src/clude_code/llm/providers/**`（多数 Provider 用于类型注解）
- `src/clude_code/llm/__init__.py`（对外导出）

因此“直接改名并全局替换 import”风险较高。

## 2. 业界对齐与问题点

- 文件名 `llama_cpp_http.py` 语义上像“llama.cpp 专用 HTTP”，但实际类 `LlamaCppHttpClient` 是 **通用 OpenAI-compatible client**，会被多个 Provider/模式复用。
- 业界常见做法是把**通用能力**命名为 `http_client.py` / `client.py`，而把**厂商实现**放在 `providers/` 下。

## 3. 方案设计（兼容优先）

### 3.1 最终结构

```
llm/
├── http_client.py        # 新：核心实现
├── llama_cpp_http.py     # 旧：兼容层（re-export）
└── ...
```

### 3.2 兼容策略

- 新增 `http_client.py` 后：
  - 旧路径 `from clude_code.llm.llama_cpp_http import ChatMessage` 仍可用
  - 新路径 `from clude_code.llm.http_client import ChatMessage` 可用
- `llama_cpp_http.py` 只保留轻量代码：
  - 标注 deprecated（软提示）
  - re-export `http_client.py` 的公开符号（含 `__all__`）

### 3.3 风险与防护

| 风险 | 说明 | 防护 |
|------|------|------|
| 循环依赖 | 新模块依赖老模块导致循环 | `http_client.py` 不 import `llama_cpp_http.py` |
| 行为差异 | 搬迁时遗漏代码 | 采用“迁移实现 + 兼容层导出”，实现只保留一份 |
| 大范围改动 | 一次性替换 import 易破坏 | 先让 `llama_cpp_http.py` 成为兼容层，后续渐进迁移 |

## 4. 实施步骤

1. 新增 `src/clude_code/llm/http_client.py`：迁移原实现
2. 改造 `src/clude_code/llm/llama_cpp_http.py`：兼容层 re-export
3. 更新 `src/clude_code/llm/__init__.py`：优先从新模块导出（外部保持不变）
4. 运行 `compileall` + 导入检查

## 5. 验收标准

- [ ] 旧 import 路径仍可用（兼容）
- [ ] 新 import 路径可用（业界命名）
- [ ] `python -m compileall -q src` 通过

---

**改造前基线**：`llama_cpp_http.py` 298 行，sha1 前缀 `342dbb35fda7`

**开始时间**：2026-01-24

## 6. 实施结果与验证

### 6.1 代码变更

- 新增：`src/clude_code/llm/http_client.py`（核心实现迁移）
- 改造：`src/clude_code/llm/llama_cpp_http.py`（兼容层 re-export）
- 更新：`src/clude_code/llm/__init__.py` 统一从 `http_client.py` 导出
- 更新：`src/clude_code/llm/base.py`、`src/clude_code/llm/model_manager.py` 的 `TYPE_CHECKING` 引用路径
- 文档更新：`src/clude_code/llm/README.md`、`docs/LLM_MODULE_NAMING_ANALYSIS.md`

### 6.2 验证结果

- 语法检查：`python -m compileall -q src` ✅ 通过
- 兼容性检查（旧/新导出同一对象）：✅ 通过
  - `compat_ok True True`

**完成时间**：2026-01-24


