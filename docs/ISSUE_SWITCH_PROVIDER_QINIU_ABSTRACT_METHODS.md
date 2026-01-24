# 问题分析：切换厂商 `qiniu` 失败（抽象方法未实现）

## 1. 现象（复现日志）

在会话内执行：

- `/provider qiniu`

报错：

> `Can't instantiate abstract class QiniuProvider with abstract methods chat_async, chat_stream`

这意味着：`QiniuProvider` 继承的抽象基类 `LLMProvider` 要求必须实现 `chat_async` / `chat_stream`，但该类未实现，导致 Python 在实例化时直接失败。

---

## 2. 排查思路（过程）

### 2.1 定位报错根因属于“类定义不完整”

该报错不是网络、认证、URL、模型不可用导致，而是 **类在构造阶段就失败**：

- 触发点：切换厂商时会从 `ProviderRegistry` / `ModelManager` 实例化目标 provider
- 失败点：Python 抽象类校验（ABCMeta）在创建对象前检查抽象方法

### 2.2 代码定位

定位文件：`src/clude_code/llm/providers/qiniu.py`

确认该类只实现了：

- `chat(...)`
- `list_models(...)`
- `get_model_info(...)`
- `set_model(...)`
- `get_model(...)`

缺失：

- `chat_async(...)`（抽象方法）
- `chat_stream(...)`（抽象方法）

---

## 3. 根因分析

### 3.1 直接根因

`LLMProvider` 在 `src/clude_code/llm/base.py` 中把以下方法定义为 `@abstractmethod`：

- `chat`
- `chat_async`
- `chat_stream`
- `list_models`

而 `QiniuProvider` 只实现了 `chat/list_models`，未实现 `chat_async/chat_stream`，因此实例化失败。

### 3.2 为什么这个问题会在“切换厂商”时暴露

项目的 `/providers` 列表来自 `ProviderRegistry.list_providers()`（只需要类属性：`PROVIDER_NAME/TYPE/REGION`），不会实例化 provider。

而 `/provider <id>` 会触发切换并实例化 provider，因此会在这一刻暴露抽象方法缺失问题。

---

## 4. 解决方案（业界对齐）

### 4.1 方案选择

| 方案 | 做法 | 优点 | 风险 |
|------|------|------|------|
| A | 修改 `LLMProvider`：为 `chat_async/chat_stream` 提供默认实现（不再 abstract） | 一劳永逸，避免同类错误 | 可能掩盖厂商不完整实现，降低约束 |
| ✅ B | 补齐 `QiniuProvider`：实现 `chat_async/chat_stream`（必要时降级为“非流式单段输出”） | 与当前抽象基类契约一致，约束清晰 | 需要在每个缺失的 provider 上补齐 |

本次采用 **方案 B**：补齐 `qiniu`，并额外做一次扫描，避免其他厂商同类问题。

### 4.2 实现细节

- `chat_async`：使用 `asyncio.to_thread(...)` 调用同步 `chat`，避免阻塞 event loop
- `chat_stream`：默认降级为“非流式”实现：调用 `chat` 后一次性 `yield` 完整文本

---

## 5. 验证与回归

- [x] `python -m compileall -q src` 通过
- [x] `ProviderRegistry.get_provider("qiniu", config)` 可成功实例化
- [x] `/provider qiniu` 不再报抽象类错误

---

## 6. 补充问题（运行时依赖缺失）

在进一步验证 `chat_stream` 降级实现时，发现 `QiniuProvider.chat()` 使用 `requests`：

> `ModuleNotFoundError: No module named 'requests'`

这会导致“切换厂商虽然成功，但一旦真正调用就失败”。为了提高鲁棒性并减少可选依赖，建议统一改用项目已依赖的 `httpx`（其他 Provider 也普遍使用）。

### 6.1 补充修复方案

- 将 `requests.post(...)` 改为 `httpx.Client().post(...)`
- 多模态内容使用 `convert_to_openai_vision_format` 进行转换（避免简单 `str(list)`）
- 保持错误信息清晰（HTTP 状态码 + response body 截断）

### 6.2 验收（补充）

- [ ] 不依赖 `requests` 也可运行（不再出现 ModuleNotFoundError）

---

**创建时间**：2026-01-24


