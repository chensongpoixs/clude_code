# 扫描与修复：多厂商 Provider 切换失败（抽象方法未实现）

## 1. 问题背景

用户在会话内 `/provider <id>` 切换厂商时，可能遇到：

> `Can't instantiate abstract class XXXProvider with abstract methods chat_async, chat_stream`

这类问题的共同特征是：Provider 实现只提供了同步 `chat()`，没有实现异步/流式抽象方法，因此在实例化时直接失败。

---

## 2. 扫描方法（静态审计）

为避免导入触发第三方依赖或联网，本次使用 AST 静态扫描：

- 脚本：`scripts/audit_providers_abstracts.py`
- 扫描目录：`src/clude_code/llm/providers/*.py`
- 关注点：
  - 是否实现 `chat/chat_async/chat_stream/list_models`
  - `__init__` 是否至少能接收 `config` 参数（部分 provider 会用到）

---

## 3. 扫描结果（摘要）

扫描输出显示：大量 provider 缺失 `chat_async/chat_stream`（典型为同步实现）。

这意味着：**只要严格把 async/stream 作为抽象方法，未来还会持续出现同类“切换失败”问题**。

---

## 4. 根因（架构层）

`LLMProvider` 抽象基类当前把 `chat_async/chat_stream` 定义为 `@abstractmethod`，导致：

- Provider 必须实现全部方法，否则无法实例化
- 但业界实践中，很多后端并不天然支持 streaming / async（或实现成本高）

---

## 5. 业界对齐的修复方案（推荐）

### 方案：将 async/stream 变为“可选能力”

在 `LLMProvider` 基类中提供默认降级实现：

- `chat_async`: `asyncio.to_thread(self.chat, ...)`
- `chat_stream`: `yield self.chat(...)`（单段输出）

并保留必须实现的抽象方法：

- `chat`
- `list_models`

这样可以：

- ✅ 一次性修复全部厂商切换失败
- ✅ 保持接口统一：调用方依旧可以使用 async/stream（只是可能降级）
- ✅ 允许后续逐步为支持 streaming 的厂商做更优实现

---

## 6. 风险与权衡

| 风险 | 说明 | 缓解 |
|------|------|------|
| 掩盖厂商能力差异 | 看起来都支持 async/stream，但可能是降级 | 在 `ModelInfo.supports_streaming` 中标注能力；文档说明降级行为 |
| 性能问题 | `to_thread` 会占用线程池 | 仅在使用 async API 时触发；后续可加自定义 executor |
| 行为差异 | stream 变成单段 yield | 明确属于降级；真正 streaming 的厂商可覆盖实现 |

---

## 7. 验收标准

- [ ] `/provider <id>` 不再因抽象方法缺失而失败（对所有 provider）
- [ ] `python -m compileall -q src` 通过
- [ ] `scripts/audit_providers_abstracts.py` 不再报告缺失 async/stream（或将脚本规则更新为“可选”）

---

**创建时间**：2026-01-24


