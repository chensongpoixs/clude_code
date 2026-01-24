# 动态厂商切换功能实现计划

## 一、需求明确

### 1.1 核心需求
- 用户可以通过 `/provider <id>` 动态切换厂商
- 配置文件有配置就用配置，没有就用代码默认值
- **不做智能降级**，尊重用户配置
- `/models` 命令应该去厂商查询真实模型列表（如果厂商支持）

### 1.2 当前问题
1. **配置读取问题**：`_switch_provider()` 可能读不到配置文件的值
2. **模型列表静态**：qiniu 等厂商的 `list_models()` 返回硬编码列表，不查询真实 API
3. **日志信息延迟**：日志显示的 provider 信息是上一次的（已修复，但需验证）

---

## 二、模块拆分与实施计划

### 模块 1：修复配置读取逻辑
**目标**：确保 `_switch_provider()` 正确读取配置文件的 provider 配置

**文件**：`src/clude_code/cli/slash_commands.py`

**问题分析**：
当前代码：
```python
provider_cfg_item = getattr(ctx.cfg.providers, provider_id, None)
```
这行代码可能有问题，因为 `ProvidersConfig` 的结构是：
```python
class ProvidersConfig:
    items: dict[str, ProviderConfigItem]
    default: str
```
应该用 `ctx.cfg.providers.get_item(provider_id)` 或 `ctx.cfg.providers.items.get(provider_id)`

**实施步骤**：
1. 分析 `ProvidersConfig` 的数据结构
2. 修正配置读取方式
3. 添加调试日志，验证读取到的配置值
4. 确保 base_url/api_key/default_model 正确传递给 ProviderConfig

---

### 模块 2：增强模型列表查询
**目标**：让 `list_models()` 去厂商真实 API 查询（对于支持的厂商）

**文件**：
- `src/clude_code/llm/providers/qiniu.py`
- `src/clude_code/llm/providers/openai_compat.py`（作为通用基类）

**设计思路**：
1. OpenAI-compatible 厂商（qiniu, ollama, deepseek 等）都支持 `GET /models` API
2. 在 `list_models()` 里先尝试调用 API
3. 如果失败（网络错误、404 等）→ 回退到静态列表
4. 缓存结果（避免频繁请求）

**实施步骤**：
1. 实现 `qiniu.list_models()` 的 API 调用逻辑
2. 添加异常处理和回退机制
3. 添加缓存（可选，避免每次 `/models` 都请求）
4. 测试：本地有服务时 vs 本地无服务时

---

### 模块 3：日志信息同步验证
**目标**：验证日志输出的 provider 信息是否正确

**文件**：`src/clude_code/orchestrator/agent_loop/llm_io.py`

**问题**：虽然已经修改了代码在 `llm_chat()` 开头更新 provider 信息，但需要验证：
1. 是否在正确的时机更新
2. 是否所有路径都覆盖到
3. 多轮对话后是否仍然正确

**实施步骤**：
1. 添加更详细的调试日志
2. 测试多轮对话场景
3. 测试切换厂商后的第一次对话

---

### 模块 4：同步会话配置
**目标**：确保 `_switch_provider()` 后，会话的 `ctx.cfg` 和 `ctx.agent` 状态一致

**文件**：`src/clude_code/cli/slash_commands.py`

**问题**：切换 provider 后，需要同步：
1. `ctx.cfg.llm.provider`
2. `ctx.cfg.llm.model`
3. `ctx.agent` 的内部状态（如果有的话）

**实施步骤**：
1. 在 `_switch_provider()` 成功后，同步 cfg
2. 验证 `/config` 命令显示的值是否正确
3. 验证下次重启会话时是否保留

---

## 三、实施优先级

### P0（必须立即修复）
- **模块 1**：配置读取逻辑（核心问题）
- **模块 4**：同步会话配置（保证一致性）

### P1（重要增强）
- **模块 2**：模型列表查询（用户体验）

### P2（验证优化）
- **模块 3**：日志信息验证（排查工具）

---

## 四、实施顺序

### 第一步：分析并修复配置读取（模块 1）
1. 分析 `ProvidersConfig` 数据结构
2. 定位配置读取的 bug
3. 修复 `_switch_provider()` 的配置读取逻辑
4. 添加调试日志
5. 验证：`/provider qiniu` 后日志输出的 base_url 是否正确

### 第二步：同步会话配置（模块 4）
1. 在 `_switch_provider()` 成功后同步 `ctx.cfg.llm.provider/model`
2. 验证：`/config` 命令显示的值是否正确
3. 验证：切换后发 LLM 请求时使用的是否是新 provider

### 第三步：增强模型列表查询（模块 2）
1. 实现 `qiniu.list_models()` 的 API 调用
2. 添加异常处理和回退
3. 验证：本地有 ollama 服务时 `/models` 显示真实模型
4. 验证：本地无服务时 `/models` 显示静态列表

### 第四步：全面验证（模块 3）
1. 重启 `clude chat`
2. `/provider qiniu` → 查看日志
3. `你好` → 查看日志（provider_id/base_url/model 是否正确）
4. `/models` → 查看模型列表
5. `/provider openai` → 切换到另一个厂商
6. 重复测试

---

## 五、验收标准

### 功能验收
- [ ] `/provider qiniu` 能成功切换，使用配置文件的 base_url
- [ ] `/models` 显示的模型列表来自厂商 API（如果支持）
- [ ] 日志输出的 provider_id/base_url/model 与实际一致
- [ ] 多次切换厂商后仍然正常工作

### 健壮性验收
- [ ] 配置文件缺失时使用默认值
- [ ] 厂商 API 调用失败时回退到静态列表
- [ ] 切换到不存在的厂商时给出明确错误提示
- [ ] 配置文件格式错误时不崩溃

### 代码质量验收
- [ ] `python -m compileall -q src` 通过
- [ ] lints 无错误
- [ ] 添加了必要的调试日志
- [ ] 异常处理完整

---

## 六、风险与注意事项

### 风险 1：配置文件里的旧配置
- **现状**：用户配置文件里有 qiniu 的旧配置（真实七牛云地址）
- **处理**：尊重用户配置，如果配置的是真实地址就用真实地址
- **建议**：在切换时给出提示，告知用户当前使用的配置

### 风险 2：多个配置源的优先级
- **配置文件** (`~/.clude/.clude.yaml`)
- **环境变量** (`QINIU_BASE_URL`)
- **代码默认值** (`DEFAULT_BASE_URL`)
- **处理**：明确优先级顺序，并在文档中说明

### 风险 3：API 调用超时
- **问题**：`/models` 调用厂商 API 可能很慢或超时
- **处理**：设置合理的超时时间（如 5 秒），超时则回退静态列表

---

**下一步**：开始实施模块 1（配置读取修复），先分析 `ProvidersConfig` 数据结构，写入思考过程文档。

