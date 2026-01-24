# 模块 1 实施：配置读取逻辑修复

## 一、问题定位

### 1.1 代码分析

#### 当前代码（`slash_commands.py::_switch_provider()`）
```python
# 第 568 行附近
provider_cfg_item = getattr(ctx.cfg.providers, provider_id, None)
if provider_cfg_item:
    config = ProviderConfig(
        name=provider_id,
        api_key=provider_cfg_item.api_key,
        base_url=provider_cfg_item.base_url,
        api_version=provider_cfg_item.api_version,
        default_model=provider_cfg_item.default_model,
        timeout_s=provider_cfg_item.timeout_s,
        extra=provider_cfg_item.extra,
    )
```

#### `ProvidersConfig` 数据结构（`config.py`）
```python
class ProvidersConfig(BaseModel):
    items: dict[str, ProviderConfigItem] = {}
    default: str = "llama_cpp"
    
    def get_item(self, provider_id: str) -> ProviderConfigItem | None:
        return self.items.get(provider_id)
```

### 1.2 根因分析

**问题**：`getattr(ctx.cfg.providers, provider_id, None)` 是错误的用法。

**原因**：
1. `ctx.cfg.providers` 是 `ProvidersConfig` 实例
2. `ProvidersConfig` 的数据在 `items` 字典里，不是作为属性
3. `getattr(ctx.cfg.providers, "qiniu", None)` 会查找 `ProvidersConfig.qiniu` 属性（不存在）

**正确用法**：
```python
provider_cfg_item = ctx.cfg.providers.get_item(provider_id)
# 或
provider_cfg_item = ctx.cfg.providers.items.get(provider_id)
```

### 1.3 影响范围

这个 bug 导致：
1. **配置文件有配置也读不到** → 总是用 `ProviderConfig(name=provider_id)` 空配置
2. **base_url/api_key 都是空** → provider 实例化时用代码里的 `DEFAULT_BASE_URL`
3. **用户以为自己的配置被使用了，实际没有**

---

## 二、修复方案

### 2.1 修复点 1：配置读取方式

**修改前**：
```python
provider_cfg_item = getattr(ctx.cfg.providers, provider_id, None)
```

**修改后**：
```python
provider_cfg_item = ctx.cfg.providers.get_item(provider_id)
```

### 2.2 修复点 2：添加调试日志

在读取配置后，添加日志输出实际读到的值：
```python
if provider_cfg_item:
    ctx.console.print(f"[dim]读取到配置: base_url={provider_cfg_item.base_url}, api_key={'***' if provider_cfg_item.api_key else '(空)'}, default_model={provider_cfg_item.default_model}[/dim]")
else:
    ctx.console.print(f"[dim]配置文件未配置 {provider_id}，将使用默认值[/dim]")
```

### 2.3 修复点 3：完善默认值处理

如果配置文件里没有配置，应该给出合理的默认值：
```python
if provider_cfg_item is None:
    # 使用默认配置
    config = ProviderConfig(name=provider_id)
    ctx.console.print(f"[yellow]⚠ 配置文件未配置 {provider_id}，将使用代码默认值[/yellow]")
    ctx.console.print(f"[dim]提示：如需自定义配置，请运行 /provider-config-set {provider_id} base_url=... api_key=...[/dim]")
else:
    # 使用配置文件的值
    config = ProviderConfig(
        name=provider_id,
        api_key=provider_cfg_item.api_key or "",
        base_url=provider_cfg_item.base_url or "",
        api_version=provider_cfg_item.api_version or "",
        default_model=provider_cfg_item.default_model or "",
        timeout_s=provider_cfg_item.timeout_s or 120,
        extra=provider_cfg_item.extra or {},
    )
    ctx.console.print(f"[dim]使用配置文件配置: base_url={config.base_url or '(默认)'}, model={config.default_model or '(自动)'}[/dim]")
```

---

## 三、实施细节

### 3.1 修改的代码行

文件：`src/clude_code/cli/slash_commands.py`

位置：`_switch_provider()` 函数，约第 568-580 行

修改内容：
1. 第 568 行：`getattr(...)` → `get_item(...)`
2. 添加配置读取后的日志输出
3. 区分"有配置"和"无配置"两种情况的处理

### 3.2 代码健壮性考虑

#### 考虑 1：配置文件格式错误
```python
try:
    provider_cfg_item = ctx.cfg.providers.get_item(provider_id)
except Exception as e:
    ctx.console.print(f"[red]读取配置失败: {e}[/red]")
    provider_cfg_item = None
```

#### 考虑 2：配置值类型错误
```python
# 确保类型正确
api_key = str(provider_cfg_item.api_key or "")
base_url = str(provider_cfg_item.base_url or "")
timeout_s = int(provider_cfg_item.timeout_s or 120)
```

#### 考虑 3：敏感信息脱敏
```python
def _mask_key(key: str) -> str:
    if not key or len(key) < 8:
        return "***"
    return f"{key[:4]}***{key[-4:]}"

# 日志输出时
ctx.console.print(f"[dim]api_key={_mask_key(config.api_key)}[/dim]")
```

---

## 四、测试计划

### 4.1 测试场景 1：配置文件有完整配置
**配置**：
```yaml
providers:
  qiniu:
    enabled: true
    base_url: "https://api.qnaigc.com/v1"
    api_key: "sk-test123"
    default_model: "qiniu-llm-v1"
```

**操作**：
```
/provider qiniu
```

**期望**：
- 日志输出："使用配置文件配置: base_url=https://api.qnaigc.com/v1, model=qiniu-llm-v1"
- 日志输出："api_key=sk-t***123"
- 实际请求时使用这个 base_url

### 4.2 测试场景 2：配置文件无配置
**配置**：
```yaml
providers:
  openai:
    ...
  # qiniu 无配置
```

**操作**：
```
/provider qiniu
```

**期望**：
- 日志输出："配置文件未配置 qiniu，将使用代码默认值"
- 日志输出提示如何配置
- 使用 `QiniuProvider.DEFAULT_BASE_URL`（当前是 `http://127.0.0.1:11434`）

### 4.3 测试场景 3：配置文件有部分配置
**配置**：
```yaml
providers:
  qiniu:
    enabled: true
    base_url: "https://api.qnaigc.com/v1"
    # api_key 和 default_model 缺失
```

**操作**：
```
/provider qiniu
```

**期望**：
- 日志输出："使用配置文件配置: base_url=https://api.qnaigc.com/v1, model=(自动)"
- 日志输出："api_key=(空)"
- base_url 使用配置的值
- default_model 使用 provider 的默认值

### 4.4 测试场景 4：多次切换
**操作**：
```
/provider qiniu
/provider openai
/provider qiniu
```

**期望**：
- 每次切换都正确读取对应的配置
- 日志输出正确
- 不会混淆不同 provider 的配置

---

## 五、验证标准

### 5.1 功能验证
- [ ] 配置文件有配置时，能正确读取 base_url/api_key/default_model
- [ ] 配置文件无配置时，使用 provider 的默认值
- [ ] 配置部分字段缺失时，缺失字段使用默认值，已有字段使用配置值
- [ ] 日志输出能清楚显示当前使用的配置来源

### 5.2 健壮性验证
- [ ] 配置文件格式错误时不崩溃
- [ ] 配置值类型不对时能容错
- [ ] 敏感信息（api_key）在日志中脱敏

### 5.3 代码质量验证
- [ ] `python -m compileall -q src/clude_code/cli/slash_commands.py` 通过
- [ ] lints 无错误
- [ ] 代码注释清晰

---

## 六、实施检查清单

- [ ] 修改 `getattr` 为 `get_item`
- [ ] 添加配置读取后的日志输出
- [ ] 区分有配置和无配置两种情况
- [ ] 添加异常处理
- [ ] 敏感信息脱敏
- [ ] 添加提示信息（如何配置）
- [ ] 编译检查
- [ ] lints 检查
- [ ] 测试场景 1-4

---

**下一步**：实施代码修改

