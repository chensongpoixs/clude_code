# 问题分析与修复：切换厂商后仍在使用 llama.cpp 模型 + `/models` 未从厂商拉取

## 1. 现象

在会话内：

- `/provider qiniu` 显示切换成功（或“已经在使用”）
- `/models` 仅显示 1 个模型（看起来是本地静态列表，而不是从厂商接口拉取）
- 更关键：实际 LLM 请求仍走 llama.cpp（表现为继续使用 `llama.cpp/openai_compat` 的 `base_url` 与 `model`）

## 2. 根因定位（代码级）

### 2.1 厂商切换只影响 ModelManager 的“展示层”，不影响真正发起请求

`src/clude_code/orchestrator/agent_loop/llm_io.py::llm_chat()` 当前直接调用：

- `assistant_text = loop.llm.chat(loop.messages)`

其中 `loop.llm` 是 `LlamaCppHttpClient`，在 `AgentLoop.__init__` 固定由 `cfg.llm.*` 初始化。

**结论**：即使 `/provider` 切换了 `ModelManager._current_provider_id`，真正请求仍由 `loop.llm` 发出，导致“切换不生效”。

### 2.2 `/provider` 读取厂商配置的方式不匹配新 ProvidersConfig 结构

`src/clude_code/cli/slash_commands.py::_switch_provider()` 用了：

- `provider_cfg_item = getattr(ctx.cfg.providers, provider_id, None)`

但 `ProvidersConfig` 已迁移为 `items: dict[str, ProviderConfigItem]` + `get_item()` 访问。

**结论**：切换时经常拿不到 `base_url/api_key/default_model`，导致 provider 用默认/空配置注册，进而 `/models` 等能力表现异常。

### 2.3 Provider 的“当前模型”字段存在分裂（以 qiniu 为例）

`src/clude_code/llm/providers/qiniu.py` 内部用 `self._model` 管理当前模型，
但 `ModelManager.get_current_model()` 读取的是 `provider.current_model`（基类字段 `self._current_model`）。

**结论**：会出现“UI 看到的 current_model 与实际请求使用的 model 不一致”，进一步放大“切换后仍在用旧模型”的错觉。

### 2.4 `/models` 的期望与现实

并不是所有厂商都提供“列举所有模型”的接口；业界一般做法是：

- 若后端提供 `/models`（OpenAI-compatible 常见）：可实时拉取
- 否则：只能展示“已知静态模型列表”或“配置的 default_model”

本项目目前多数 provider 采用静态列表，因此 `/models` 可能只显示 1 个。

## 3. 业界对齐的修复方案（本次实现）

### 3.1 让 llm_io 的统一出口真正走当前 Provider

在 `llm_io.llm_chat()` 中：

- 优先使用 `ModelManager.get_current_provider()` 发起请求（`provider.chat(...)`）
- 若未注册 provider，才回退 `loop.llm.chat(...)`

并把“实际使用的 provider_id/base_url/model”写入日志，避免再次误判。

### 3.2 修复 `/provider` 的配置读取方式

将 `getattr(ctx.cfg.providers, provider_id, None)` 改为：

- `ctx.cfg.providers.get_item(pid)`（并使用 normalize_provider_id）

确保注册 provider 时使用到正确的 `base_url/api_key/default_model/timeout_s/extra`。

### 3.3 统一 qiniu 的模型状态字段，并支持从 `/models` 拉取（可用时）

- qiniu provider 使用基类 `current_model` 作为唯一事实源
- `list_models()` 优先尝试从 `${base_url}/models` 拉取（OpenAI-compatible）
  - 拉取失败/为空则回退静态 `MODELS`

### 3.4 切换厂商时的模型兜底

在 `ModelManager.switch_provider()` 中：

- 若新厂商 `current_model` 为空：自动选择 `default_model` 或 `list_models()[0]`

保证“切换后实际请求的 model”稳定可解释。

## 4. 验收点

- `/provider qiniu` 后，后续 LLM 请求由 qiniu provider 发起（日志可见 provider 信息）
- `/models` 对 qiniu：若后端支持 `/models`，应展示远端列表；否则回退静态列表但不报错
- 全量 `python -m compileall -q src` 通过

## 5. 相关改动文件

- `src/clude_code/orchestrator/agent_loop/llm_io.py`
- `src/clude_code/cli/slash_commands.py`
- `src/clude_code/llm/model_manager.py`
- `src/clude_code/llm/providers/qiniu.py`

（创建时间：2026-01-24）


