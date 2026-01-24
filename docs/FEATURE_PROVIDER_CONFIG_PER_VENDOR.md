# 多厂商独立配置与配置查询能力（默认 llama.cpp）设计与开发计划

## 1. 背景与目标

用户诉求：

1. **每个厂商都可以单独配置** `base_url / api_key / timeout / default_model / extra...`
2. **可以获取每个厂商（模型厂家）的配置所有信息**（用于诊断、展示、审计）
3. **默认使用 llama.cpp 厂商**
4. 需要把**思考流程、实现流程、开发计划**写入文档，符合业界实践

---

## 2. 现状盘点（项目当前能力）

### 2.1 已具备：多厂商配置模型

`src/clude_code/config/config.py` 已有：

- `ProviderConfigItem`：单厂商配置（enabled/api_key/base_url/api_version/organization/default_model/timeout_s/extra）
- `ProvidersConfig`：多厂商配置容器（字段形式列出 openai/anthropic/…/llama_cpp/openai_compat）

### 2.2 已具备：多厂商运行时抽象

`src/clude_code/llm` 已有：

- `LLMProvider` 抽象基类（统一 `chat/list_models/...`）
- `ProviderRegistry`（注册与实例化）
- `ModelManager`（当前厂商/模型切换）

### 2.3 当前缺口（为什么还需要做）

| 缺口 | 影响 |
|------|------|
| **配置查询接口缺失** | 无法“查看某厂商/所有厂商配置”的完整信息（尤其是 `extra`） |
| **安全脱敏缺失** | 直接 dump 配置会泄露 `api_key` |
| **默认厂商不统一** | `LLMConfig.provider`/`ProvidersConfig.default`/向导预设存在历史值与不一致 |
| **兼容映射缺失** | 旧值（如 `llama_cpp_http`）需要平滑映射到 `llama_cpp` |

---

## 3. 业界对齐（推荐实践）

### 3.1 配置层（Dify/LiteLLM/LangChain 的共识）

- **按 provider_id 分组配置**：`providers.<id>.base_url/api_key/...`
- **默认厂商字段**：`providers.default = "<id>"`
- **敏感字段默认不输出**：展示时输出 `api_key` 的 mask（如 `sk-***abcd`）
- **支持扩展字段**：`extra` 允许厂商特有参数（如 llama.cpp 的 `n_ctx`、`repeat_penalty`）

### 3.2 运行时层（策略）

- **统一 provider 实例化入口**（registry + config 转换）
- **配置查询与诊断命令**：CLI / slash command 提供 “show provider config”

---

## 4. 设计方案（模块功能视角）

### 4.1 配置结构（最终推荐）

```yaml
providers:
  default: llama_cpp
  llama_cpp:
    enabled: true
    base_url: "http://127.0.0.1:8899"
    api_key: ""           # 可选
    default_model: "auto"
    timeout_s: 120
    extra:
      api_mode: "openai_compat"
      n_ctx: 32768
      repeat_penalty: 1.1

  openai:
    enabled: false
    base_url: "https://api.openai.com/v1"
    api_key: "${OPENAI_API_KEY}"
    default_model: "gpt-4o"
```

> 说明：`providers.<id>` 对应 `ProviderRegistry.register("<id>")` 的 provider_id。

### 4.2 默认 llama.cpp 的统一策略

需要统一 3 个地方：

1. `ProvidersConfig.default`：默认应为 `llama_cpp`
2. `LLMConfig.provider`（legacy 字段）：默认也应为 `llama_cpp`（或标记 deprecated）
3. `config_wizard` 预设与交互选择：默认优先 `llama_cpp`

并提供兼容映射：

- `"llama_cpp_http"` → `"llama_cpp"`（历史值）

### 4.3 “获取所有配置”的 API 设计（脱敏）

在 `ProvidersConfig` 上提供：

- `get_item(provider_id) -> ProviderConfigItem | None`
- `list_items() -> dict[str, ProviderConfigItem]`
- `to_public_dict(include_disabled=True) -> dict`（对 `api_key` 做 mask，保留 `extra`）

在 `CludeConfig` 上提供（更接近业务）：

- `get_effective_provider_id()`：优先 `providers.default`，其次 legacy `llm.provider`
- `get_effective_provider_item(provider_id=None)`：取当前/指定 provider 的完整配置

### 4.4 CLI / Slash 命令（用于“查看所有信息”）

建议增加两类接口：

#### A) Slash Commands（会话内）

- `/provider-config [id]`：显示指定厂商的配置（脱敏）
- `/provider-configs`：列出所有厂商配置摘要（脱敏，含 enabled/base_url/default_model/timeout）

#### B) CLI 命令（非会话）

- `clude providers config [id]`
- `clude providers config --all`

> 先实现 Slash Commands（更贴近当前工作流），CLI 后续补齐。

---

## 5. 实现流程（按步骤）

### Step 1：文档与兼容策略落地（P0）

- 输出本设计文档（本文件）
- 明确：默认 llama.cpp + 兼容映射 + 脱敏策略

### Step 2：配置层实现（P1）

- `ProvidersConfig.default` 设为 `llama_cpp`
- `LLMConfig.provider` 默认改为 `llama_cpp`
- 配置加载后做 normalize：`llama_cpp_http -> llama_cpp`
- `config_wizard` 预设与 provider 列表同步更新

### Step 3：配置查询实现（P2）

实现：

- `ProvidersConfig.to_public_dict()`
- `CludeConfig.get_effective_provider_id()` 等方法

并在 Slash Commands 中加入：

- `/provider-config`
- `/provider-configs`

### Step 4：验证与回归（P3）

验证项：

- `python -m compileall -q src`
- `slash_commands` 中输出脱敏正确（不会打印完整 api_key）
- 兼容：旧配置 `llama_cpp_http` 仍能正常工作

---

## 8. 当前实现进度（2026-01-24）

- ✅ 默认厂商已统一为 `llama_cpp`
  - `LLMConfig.provider = "llama_cpp"`
  - `ProvidersConfig.default = "llama_cpp"`
  - `config_wizard` 预设与交互已同步为 `llama_cpp`
- ✅ 兼容映射已加入：`llama_cpp_http -> llama_cpp`
- ✅ 配置查询 API（脱敏）已实现：
  - `ProvidersConfig.list_items() / get_item() / to_public_dict()`
  - `CludeConfig.get_effective_provider_id()`
- ✅ Slash Commands 已提供：
  - `/provider-configs`（列表摘要）
  - `/provider-config <id>`（单个详情，脱敏）

---

## 6. 风险评估与缓解

| 风险 | 等级 | 说明 | 缓解 |
|------|------|------|------|
| 泄露 api_key | 高 | “获取所有信息”很容易直接输出密钥 | 强制脱敏输出；只允许显式 include_secrets 才输出明文（默认禁止） |
| 默认值不一致 | 中 | `llm.provider` vs `providers.default` 冲突 | 定义“effective provider”规则并实现 normalize |
| 兼容破坏 | 中 | 老配置值 `llama_cpp_http` | 加映射表并记录日志提示 |
| CLI 输出过长 | 中 | `extra` 可能很大 | 输出分级：摘要 + 可选 `--verbose` |

---

## 7. 交付物清单

### 文档

- `docs/FEATURE_PROVIDER_CONFIG_PER_VENDOR.md`（本文件）

### 代码（计划）

- `src/clude_code/config/config.py`：默认值/normalize/API
- `src/clude_code/config/config_wizard.py`：预设与交互更新
- `src/clude_code/cli/slash_commands.py`：新增 `/provider-config(s)`

---

**创建时间**：2026-01-24


