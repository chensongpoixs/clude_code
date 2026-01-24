# CLI 配置厂商 base_url/api_key 并更新配置文件 + /help 补全（实现思路与计划）

## 1. 需求拆解

目标：

1. **命令行配置**：可分别为某个厂商设置 `base_url`、`api_key` 等
2. **更新配置文件**：写入 `~/.clude/.clude.yaml`
3. **/help 文档补全**：在会话内 `/help` 中补充相关命令说明与示例

---

## 2. 现状与问题

### 2.1 ProvidersConfig 原先是“固定字段”

之前 `ProvidersConfig` 是 `openai/anthropic/...` 这种“写死字段”的结构，导致：

- 新增厂商（47 个）无法全部在配置层表达（只能表达 12 个）
- 即使 CLI 写入 YAML，加载时也会丢弃未知字段（Pydantic extra ignore）

### 2.2 业界最佳实践

业界（Dify / LiteLLM / LangChain 生态）通常使用：

```yaml
providers:
  default: llama_cpp
  openai:
    base_url: ...
    api_key: ...
  llama_cpp:
    base_url: ...
    extra:
      n_ctx: 32768
```

也就是 **providers 下允许任意 provider_id 作为 key**。

---

## 3. 方案设计

### 3.1 配置层：ProvidersConfig 改为动态 items（并保持 YAML 结构）

- 内部存储：`items: Dict[str, ProviderConfigItem]`
- 输入兼容：把 `providers` 下除 `default` 外的所有 key 都收敛为 items
- 输出序列化：通过 `model_serializer` 把 items “flatten” 回 `providers.<id>`，保持 YAML 结构不变

### 3.2 CLI：新增 `clude providers set/show`

#### `clude providers set`

能力：

- `--base-url / --api-key / --enabled/--disabled / --default-model / --timeout-s / --extra key=value`
- `--set-default`：同时把 `providers.default`（以及 legacy `llm.provider`）设为该厂商
- 保存到 `~/.clude/.clude.yaml`
- 输出时对 api_key 脱敏

#### `clude providers show`

- 不带参数：列出所有厂商配置摘要（脱敏）
- 带 `provider_id`：展示单个厂商配置（脱敏）

### 3.3 /help 补全

在 `src/clude_code/cli/slash_commands.py` 的 `/help` 输出中增加：

- `CLI: clude providers set <id> ...` 的用法说明

---

## 4. 风险与缓解

| 风险 | 等级 | 说明 | 缓解 |
|------|------|------|------|
| api_key 泄露 | 高 | CLI/show 可能把 key 打印出来 | 强制脱敏输出；仅写入配置文件明文 |
| 配置兼容性 | 中 | 老 YAML 结构读取/保存 | before-validator 收敛 + serializer flatten |
| 误写配置文件 | 中 | 写到用户 home | 命令输出提示保存位置；后续可加 `--config-path` |
| extra 过大 | 低 | extra 字段太长 | CLI 支持多次 `--extra`，展示时仍保留 |

---

## 5. 实施步骤（按模块）

1. **配置层**：调整 `ProvidersConfig` 为动态结构（validator + serializer）
2. **CLI 层**：新增 `providers_cmd.py` + 注册到 `main.py`
3. **Help**：补全 `/help` 文档输出
4. **校验**：`compileall` + 基础运行导入 + lints

---

## 6. 验收标准

- [ ] `clude providers set openai --base-url ... --api-key ...` 后，`~/.clude/.clude.yaml` 被更新
- [ ] `clude providers show` 能看到脱敏后的配置
- [ ] `/help` 中包含 CLI 配置说明
- [ ] `python -m compileall -q src` 通过

---

**创建时间**：2026-01-24


