# llama_cpp_http.py → http_client.py 完整迁移方案

## 1. 问题分析

### 1.1 命名冲突问题

当前 `llama_cpp_http.py` 存在以下问题：

| 问题类型 | 说明 | 影响 |
|---------|------|------|
| **语义混淆** | 文件名暗示"llama.cpp 专用"，但实际是通用 HTTP 客户端 | 新开发者误解用途 |
| **厂商冲突** | `src/clude_code/llm/providers/llama_cpp.py` 是真正的 llama.cpp Provider | 命名空间冲突 |
| **可维护性** | 通用功能用厂商名命名，不符合模块职责单一原则 | 代码难以理解 |

### 1.2 当前状态（P3 已完成）

```
llm/
├── http_client.py           # ✅ 新：核心实现
├── llama_cpp_http.py        # ⚠️ 旧：兼容层（re-export）
└── providers/
    └── llama_cpp.py         # ✅ 真正的 llama.cpp 厂商实现
```

**现状**：
- `http_client.py` 已包含完整实现
- `llama_cpp_http.py` 仅作为兼容层（15 行代码）
- 全项目 55+ 处仍使用 `from clude_code.llm.llama_cpp_http import ...`

---

## 2. 业界对比

### 2.1 业界命名规范

| 框架 | 通用客户端命名 | 厂商实现位置 |
|------|---------------|-------------|
| **LangChain** | `langchain/chat_models/base.py` | `langchain/chat_models/openai.py` |
| **LiteLLM** | `litellm/utils.py` | `litellm/llms/openai.py` |
| **Dify** | `core/model_runtime/model_providers/__base/` | `core/model_runtime/model_providers/openai/` |
| **OpenAI SDK** | `openai/_client.py` | - |
| **本项目** | `llm/http_client.py` ✅ | `llm/providers/llama_cpp.py` ✅ |

**结论**：业界通用客户端使用 `client.py` / `base.py` / `http_client.py`，厂商实现放在 `providers/` 下。

### 2.2 业界迁移策略

| 策略 | 说明 | 风险 | 适用场景 |
|------|------|------|---------|
| **Big Bang** | 一次性全局替换所有引用 | 高 | 小项目 |
| **兼容层 + 渐进迁移** | 保留旧模块作为别名，逐步迁移 | 低 | 中大型项目（推荐） |
| **Deprecation Warning** | 旧模块添加警告，强制迁移 | 中 | 有版本管理的项目 |

**本项目选择**：兼容层 + 渐进迁移（风险最低）

---

## 3. 迁移计划（分阶段）

### 阶段 1: 核心模块迁移（已完成 ✅）

**目标**：新增 `http_client.py`，`llama_cpp_http.py` 改为兼容层

**完成内容**：
- [x] 新增 `src/clude_code/llm/http_client.py`（312 行）
- [x] 改造 `src/clude_code/llm/llama_cpp_http.py` 为兼容层（33 行）
- [x] 更新 `llm/__init__.py` 优先从 `http_client` 导出
- [x] 更新 `TYPE_CHECKING` 引用路径（`base.py`, `model_manager.py`）
- [x] 文档更新（`README.md`, `LLM_MODULE_NAMING_ANALYSIS.md`）

**验收**：
- `python -m compileall -q src` ✅ 通过
- 兼容性测试 ✅ `ChatMessage is ChatMessage` → `True`

---

### 阶段 2: 逐步迁移引用（进行中 🔄）

**目标**：将项目中的 55+ 处引用逐步迁移到 `http_client`

#### 2.1 迁移优先级与进度

| 优先级 | 模块 | 引用数 | 风险 | 状态 | 说明 |
|--------|------|--------|------|------|------|
| **P0** | `llm/__init__.py` | 1 | 低 | ✅ 完成 | 对外 API（阶段 1） |
| **P1** | `llm/base.py`, `llm/model_manager.py` | 2 | 低 | ✅ 完成 | 核心模块（阶段 1） |
| **P2** | `llm/providers/**` (48 个) | 29 | 低 | ✅ 完成 | 类型注解（2026-01-24） |
| **P3** | `orchestrator/**` | 6 | 高 | 🔄 待实施 | 核心逻辑，需充分测试 |
| **P4** | `cli/**` | 6 | 中 | 🔄 待实施 | 用户交互，需手动验证 |
| **其他** | `failover/streaming/plugins` | 4 | 低 | 🔄 待实施 | 辅助模块 |

#### 2.2 P2: Providers 模块迁移

**影响文件** (47 个)：
```python
# 当前
from ..llama_cpp_http import ChatMessage

# 目标
from ..http_client import ChatMessage
```

**实施方式**：
```bash
# 批量替换（PowerShell）
Get-ChildItem src/clude_code/llm/providers/*.py | ForEach-Object {
    (Get-Content $_) -replace 'from \.\.llama_cpp_http import', 'from ..http_client import' | Set-Content $_
}
```

**风险**：
- **低**：仅类型注解，不影响运行时
- 验证：`python -m compileall -q src/clude_code/llm/providers`

#### 2.3 P3: Orchestrator 模块迁移

**影响文件** (6 个)：
```python
src/clude_code/orchestrator/
├── agent_loop/
│   ├── agent_loop.py       # from clude_code.llm.llama_cpp_http import ...
│   ├── execution.py
│   ├── planning.py
│   ├── llm_io.py
│   └── react.py
├── classifier.py
└── advanced_context.py
```

**实施方式**：
```bash
# 逐个文件替换并测试
sed -i 's/from clude_code\.llm\.llama_cpp_http/from clude_code.llm.http_client/g' src/clude_code/orchestrator/**/*.py
```

**风险**：
- **高**：核心执行逻辑，需要：
  1. 单元测试覆盖
  2. 集成测试验证
  3. 手动运行 `clude chat` 验证

#### 2.4 P4: CLI 模块迁移

**影响文件** (6 个)：
```python
src/clude_code/cli/
├── chat_handler.py
├── doctor_cmd.py
├── info_cmds.py
├── session_store.py
├── utils.py
└── config_wizard.py
```

**风险**：
- **中**：用户交互入口，需要：
  1. `clude chat` 功能测试
  2. `clude doctor` 功能测试
  3. `clude config` 功能测试

---

### 阶段 3: 移除兼容层（可选）

**目标**：完全移除 `llama_cpp_http.py`

**前置条件**：
- [x] 阶段 2 全部完成
- [ ] 全项目搜索确认无 `llama_cpp_http` 引用
- [ ] 外部项目（如果有）已更新

**实施**：
```bash
# 1. 确认无引用
grep -r "llama_cpp_http" src/

# 2. 删除文件
rm src/clude_code/llm/llama_cpp_http.py

# 3. 更新文档
```

**风险**：
- **高**：外部依赖可能破坏
- **缓解**：保留兼容层至少 1-2 个版本

---

## 4. 模块功能实现细节

### 4.1 http_client.py 核心功能

```python
# 文件: src/clude_code/llm/http_client.py (312 行)

# 1. 消息模型
@dataclass
class ChatMessage:
    role: Literal["system", "user", "assistant"]
    content: str | list[dict]  # 支持多模态

# 2. 通用 HTTP 客户端
class LlamaCppHttpClient:
    def __init__(self, base_url, api_mode, model, ...): ...
    def chat(self, messages: list[ChatMessage]) -> str: ...
    def list_model_ids(self) -> list[str]: ...
    def _chat_openai_compat(self, messages) -> str: ...
    def _chat_completion(self, messages) -> str: ...
```

**职责**：
- OpenAI-compatible API 通信
- 多模态消息格式转换（Claude Vision → OpenAI Vision）
- 模型发现与切换
- 错误处理与重试

### 4.2 llama_cpp_http.py 兼容层

```python
# 文件: src/clude_code/llm/llama_cpp_http.py (33 行)

"""
兼容层：将旧的 llama_cpp_http 引用重定向到 http_client

已弃用（Deprecated）：
- 建议使用: from clude_code.llm.http_client import ChatMessage
- 此文件将在未来版本移除
"""

from .http_client import (
    ChatMessage,
    LlamaCppHttpClient,
    Role,
    ContentPart,
    MultimodalContent,
    LLMProvider,
)

__all__ = [
    "ChatMessage",
    "LlamaCppHttpClient",
    "Role",
    "ContentPart",
    "MultimodalContent",
    "LLMProvider",
]
```

**特点**：
- 仅 re-export，无逻辑
- 保持 API 100% 兼容
- 添加 Deprecation 注释

---

## 5. 风险评估与缓解

### 5.1 风险矩阵

| 风险 | 概率 | 影响 | 等级 | 缓解措施 |
|------|------|------|------|---------|
| **循环依赖** | 低 | 高 | 中 | `http_client.py` 不导入 `llama_cpp_http.py` |
| **运行时错误** | 低 | 高 | 中 | 保留兼容层，渐进迁移 |
| **类型检查失败** | 中 | 中 | 中 | 同步更新 `TYPE_CHECKING` |
| **外部依赖破坏** | 低 | 高 | 中 | 保留兼容层至少 1-2 版本 |
| **测试覆盖不足** | 中 | 高 | 高 | 增加集成测试 |

### 5.2 回滚方案

| 阶段 | 回滚步骤 | 成本 |
|------|---------|------|
| **阶段 1** | 删除 `http_client.py`，恢复 `llama_cpp_http.py` | 低 |
| **阶段 2** | 恢复 Git 分支 | 中 |
| **阶段 3** | 恢复 `llama_cpp_http.py` 兼容层 | 高 |

---

## 6. 验收标准

### 6.1 功能验收

- [ ] 所有现有功能正常运行
- [ ] `clude chat` 可正常对话
- [ ] `clude doctor` 检查通过
- [ ] 多模态图片分析正常

### 6.2 代码质量

- [ ] `python -m compileall -q src` 通过
- [ ] 无 linter 错误
- [ ] 类型检查通过（如果有 mypy）
- [ ] 单元测试通过（如果有）

### 6.3 文档完整性

- [ ] README 更新
- [ ] API 文档更新
- [ ] 迁移指南提供
- [ ] CHANGELOG 记录

---

## 7. 实施时间表

| 阶段 | 工作量 | 时间 | 状态 |
|------|--------|------|------|
| **阶段 1: 核心迁移** | 4h | 2026-01-24 | ✅ 完成 |
| **阶段 2-P2: Providers** | 15min | 2026-01-24 | ✅ 完成 |
| **阶段 2-P3: Orchestrator** | 10min | 2026-01-24 | ✅ 完成 |
| **阶段 2-P4+其他: CLI/辅助** | 10min | 2026-01-24 | ✅ 完成 |
| **阶段 3: 移除兼容层** | 1h | 待定 (v2.0) | ⏸️ 暂缓 |

---

## ✅ 阶段 2 完成汇报

**迁移完成时间**: 2026-01-24  
**总文件数**: 44 个  
**成功率**: 100%  
**详细报告**: 见 `docs/STAGE2_MIGRATION_COMPLETE_REPORT.md`

---

## 8. 下一步行动

### 立即行动（推荐）

1. **批量迁移 Providers**（P2，低风险）
   ```bash
   python scripts/migrate_imports.py --module providers --dry-run
   python scripts/migrate_imports.py --module providers --execute
   ```

2. **逐个迁移 Orchestrator**（P3，高风险）
   - 先迁移 `llm_io.py`（最底层）
   - 再迁移 `planning.py`, `execution.py`, `react.py`
   - 最后迁移 `agent_loop.py`

3. **手动测试 CLI**（P4）
   - 运行 `clude chat` 完整对话流程
   - 运行 `clude doctor` 检查
   - 运行 `clude config` 配置

### 长期计划（可选）

1. **添加 Deprecation Warning**
   ```python
   # llama_cpp_http.py
   import warnings
   warnings.warn(
       "llama_cpp_http is deprecated, use http_client instead",
       DeprecationWarning,
       stacklevel=2
   )
   ```

2. **发布迁移指南**
   - 创建 `docs/MIGRATION_GUIDE.md`
   - 在 CHANGELOG 中说明

3. **版本计划**
   - v1.x: 保留兼容层
   - v2.0: 移除兼容层（Breaking Change）

---

## 9. 相关文档

- `docs/IMPL_LLM_HTTP_CLIENT_P3.md` - 阶段 1 实施记录
- `docs/LLM_MODULE_NAMING_ANALYSIS.md` - 命名规范分析
- `docs/IMPL_LLM_NAMING_IMPROVEMENTS.md` - P1/P2 实施记录
- `src/clude_code/llm/README.md` - LLM 模块文档

---

**创建时间**: 2026-01-24  
**最后更新**: 2026-01-24  
**状态**: 阶段 1 完成，阶段 2 待实施

