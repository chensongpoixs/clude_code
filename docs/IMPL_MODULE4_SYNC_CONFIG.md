# 模块 4 实施：同步会话配置

## 一、问题定位

### 1.1 需求分析
当用户执行 `/provider qiniu` 切换厂商后，需要确保：
1. `ctx.cfg.llm.provider` 显示的是 "qiniu"（而不是旧的 "llama_cpp"）
2. `ctx.cfg.llm.model` 显示的是 qiniu 的当前模型（而不是旧的 gemma 模型）
3. `/config` 命令显示的配置与实际使用的一致
4. 下一轮对话时，LLM 请求使用的确实是 qiniu provider

### 1.2 当前代码分析

#### 代码位置：`slash_commands.py::_switch_provider()`
```python
# 第 602-613 行
success, message = mm.switch_provider(pid)
if success:
    ctx.console.print(f"[green]✓ {message}[/green]")
    # 同步到会话 cfg（避免"已切换但 cfg 仍显示旧值"）
    try:
        ctx.cfg.llm.provider = pid
        # 切换厂商后，默认把会话模型同步为当前厂商模型（避免继续显示/使用旧模型）
        cm = mm.get_current_model()
        if cm:
            ctx.cfg.llm.model = cm
    except Exception:
        pass
```

**现状**：代码已经尝试同步 `ctx.cfg.llm.provider` 和 `ctx.cfg.llm.model`

### 1.3 潜在问题

#### 问题 1：异常被静默吞掉
```python
except Exception:
    pass  # 如果同步失败，用户不知道
```
如果同步失败，用户看到"✓ 已切换"，但实际 cfg 没更新。

#### 问题 2：没有同步 base_url
`ctx.cfg.llm.base_url` 仍然是旧的 `http://127.0.0.1:8899`，虽然实际请求已经走新 provider，但 `/config` 显示的是错的。

#### 问题 3：没有验证同步结果
同步后没有验证是否成功，用户无法确认。

---

## 二、修复方案

### 2.1 增强同步逻辑

#### 目标
1. **同步 provider ID**：`ctx.cfg.llm.provider = pid`
2. **同步 model**：`ctx.cfg.llm.model = current_model`
3. **同步 base_url**：`ctx.cfg.llm.base_url = provider_base_url`
4. **同步 api_mode**：保持 `openai_compat`（大部分 provider 都是这个模式）
5. **异常处理**：如果同步失败，给出明确提示

#### 实现策略
```python
# 执行切换
success, message = mm.switch_provider(pid)
if success:
    ctx.console.print(f"[green]✓ {message}[/green]")
    
    # 同步会话配置
    sync_failed = False
    try:
        # 获取切换后的 provider 信息
        current_provider = mm.get_provider()
        current_model = mm.get_current_model()
        
        # 同步到 ctx.cfg
        ctx.cfg.llm.provider = pid
        ctx.cfg.llm.model = current_model or ""
        
        # 同步 base_url（如果 provider 有配置）
        if current_provider and hasattr(current_provider, "config"):
            provider_cfg = current_provider.config
            if provider_cfg.base_url:
                ctx.cfg.llm.base_url = provider_cfg.base_url
        
        # 验证同步结果
        if ctx.cfg.llm.provider != pid:
            sync_failed = True
            ctx.console.print(f"[yellow]⚠ 配置同步异常：provider 未更新[/yellow]")
        
    except Exception as e:
        sync_failed = True
        ctx.console.print(f"[yellow]⚠ 配置同步失败: {e}[/yellow]")
        if ctx.debug:
            import traceback
            ctx.console.print(f"[dim]{traceback.format_exc()}[/dim]")
    
    # 显示同步结果
    if not sync_failed:
        ctx.console.print(f"[dim]✓ 会话配置已同步: provider={ctx.cfg.llm.provider}, model={ctx.cfg.llm.model}[/dim]")
```

### 2.2 添加配置验证

在同步后，验证配置是否正确：
```python
def _verify_config_sync(ctx: SlashContext, expected_provider: str) -> bool:
    """验证配置同步是否成功"""
    if ctx.cfg.llm.provider != expected_provider:
        return False
    
    # 可选：验证 model 是否合理
    model = ctx.cfg.llm.model
    if not model:
        ctx.console.print("[yellow]⚠ 当前模型为空[/yellow]")
    
    return True
```

### 2.3 增强用户反馈

同步成功后，给出详细信息：
```python
# 显示当前配置
ctx.console.print(f"[dim]当前配置:[/dim]")
ctx.console.print(f"[dim]  - 厂商: {ctx.cfg.llm.provider}[/dim]")
ctx.console.print(f"[dim]  - 模型: {current_model}[/dim]")
if hasattr(current_provider, "config") and current_provider.config.base_url:
    ctx.console.print(f"[dim]  - 端点: {current_provider.config.base_url}[/dim]")
```

---

## 三、实施细节

### 3.1 修改位置

文件：`src/clude_code/cli/slash_commands.py`  
函数：`_switch_provider()`  
位置：第 602-620 行

### 3.2 修改内容

#### 修改前
```python
success, message = mm.switch_provider(pid)
if success:
    ctx.console.print(f"[green]✓ {message}[/green]")
    # 同步到会话 cfg（避免"已切换但 cfg 仍显示旧值"）
    try:
        ctx.cfg.llm.provider = pid
        # 切换厂商后，默认把会话模型同步为当前厂商模型（避免继续显示/使用旧模型）
        cm = mm.get_current_model()
        if cm:
            ctx.cfg.llm.model = cm
    except Exception:
        pass
    # 显示当前模型
    current_model = mm.get_current_model()
    if current_model:
        ctx.console.print(f"[dim]当前模型: {current_model}[/dim]")
    # 显示可用模型数
    models = mm.list_models()
    ctx.console.print(f"[dim]可用模型: {len(models)} 个[/dim]")
```

#### 修改后
```python
success, message = mm.switch_provider(pid)
if success:
    ctx.console.print(f"[green]✓ {message}[/green]")
    
    # 同步会话配置（详细版）
    try:
        current_provider = mm.get_provider()
        current_model = mm.get_current_model()
        
        # 同步核心字段
        ctx.cfg.llm.provider = pid
        ctx.cfg.llm.model = current_model or ""
        
        # 同步 base_url（如果 provider 有配置）
        if current_provider and hasattr(current_provider, "config"):
            provider_cfg = getattr(current_provider, "config", None)
            if provider_cfg and hasattr(provider_cfg, "base_url") and provider_cfg.base_url:
                ctx.cfg.llm.base_url = provider_cfg.base_url
        
        # 显示同步结果
        ctx.console.print(f"[dim]✓ 会话配置已同步[/dim]")
        ctx.console.print(f"[dim]  • 厂商: {ctx.cfg.llm.provider}[/dim]")
        ctx.console.print(f"[dim]  • 模型: {current_model or '(未设置)'}[/dim]")
        if current_provider and hasattr(current_provider, "config"):
            provider_cfg = getattr(current_provider, "config", None)
            if provider_cfg and hasattr(provider_cfg, "base_url"):
                ctx.console.print(f"[dim]  • 端点: {provider_cfg.base_url or '(默认)'}[/dim]")
        
    except Exception as e:
        ctx.console.print(f"[yellow]⚠ 配置同步失败: {e}[/yellow]")
        if ctx.debug:
            import traceback
            ctx.console.print(f"[dim]{traceback.format_exc()}[/dim]")
    
    # 显示可用模型数
    try:
        models = mm.list_models()
        ctx.console.print(f"[dim]可用模型: {len(models)} 个[/dim]")
    except Exception:
        pass
```

---

## 四、健壮性考虑

### 4.1 异常处理

#### 场景 1：provider 实例没有 config 属性
```python
if hasattr(current_provider, "config"):
    provider_cfg = current_provider.config
else:
    provider_cfg = None
```

#### 场景 2：config 没有 base_url 属性
```python
if provider_cfg and hasattr(provider_cfg, "base_url"):
    ctx.cfg.llm.base_url = provider_cfg.base_url
```

#### 场景 3：current_model 为空
```python
ctx.cfg.llm.model = current_model or ""
ctx.console.print(f"[dim]  • 模型: {current_model or '(未设置)'}[/dim]")
```

### 4.2 调试支持

添加 debug 模式下的详细输出：
```python
if ctx.debug:
    ctx.console.print(f"[dim]DEBUG: provider type: {type(current_provider)}[/dim]")
    ctx.console.print(f"[dim]DEBUG: config type: {type(provider_cfg)}[/dim]")
    ctx.console.print(f"[dim]DEBUG: base_url: {getattr(provider_cfg, 'base_url', None)}[/dim]")
```

---

## 五、测试计划

### 5.1 测试场景 1：切换到有配置的厂商
**前置条件**：配置文件有 qiniu 配置
```yaml
providers:
  qiniu:
    base_url: "https://api.qnaigc.com/v1"
    api_key: "sk-test"
```

**操作**：
```
/provider qiniu
```

**期望输出**：
```
✓ 已切换到厂商: qiniu
✓ 会话配置已同步
  • 厂商: qiniu
  • 模型: qiniu-llm-v1
  • 端点: https://api.qnaigc.com/v1
可用模型: 1 个
```

**验证**：
```
/config
# 应该显示：
# - llm.provider: qiniu
# - llm.model: qiniu-llm-v1
# - llm.base_url: https://api.qnaigc.com/v1
```

### 5.2 测试场景 2：切换到无配置的厂商
**前置条件**：配置文件没有 deepseek 配置

**操作**：
```
/provider deepseek
```

**期望输出**：
```
⚠ 配置文件未配置 deepseek，将使用代码默认值
✓ 已切换到厂商: deepseek
✓ 会话配置已同步
  • 厂商: deepseek
  • 模型: deepseek-chat
  • 端点: (默认) 或实际的默认 URL
可用模型: 1 个
```

### 5.3 测试场景 3：多次切换
**操作**：
```
/provider qiniu
/config  # 验证
/provider openai
/config  # 验证
/provider qiniu
/config  # 验证
```

**期望**：每次 `/config` 都显示正确的当前 provider/model/base_url

---

## 六、验收标准

### 6.1 功能验收
- [ ] 切换 provider 后，`ctx.cfg.llm.provider` 正确更新
- [ ] 切换 provider 后，`ctx.cfg.llm.model` 正确更新
- [ ] 切换 provider 后，`ctx.cfg.llm.base_url` 正确更新（如果 provider 有配置）
- [ ] `/config` 命令显示的值与实际一致
- [ ] 多次切换后配置仍然正确

### 6.2 健壮性验收
- [ ] provider 没有 config 属性时不崩溃
- [ ] config 没有 base_url 属性时不崩溃
- [ ] current_model 为空时显示 "(未设置)"
- [ ] 同步失败时给出明确提示

### 6.3 用户体验验收
- [ ] 同步成功时给出清晰的反馈
- [ ] 显示实际使用的配置（厂商/模型/端点）
- [ ] 异常时给出可操作的提示

---

## 七、实施检查清单

- [ ] 修改 `_switch_provider()` 的配置同步逻辑
- [ ] 添加 base_url 同步
- [ ] 添加同步结果验证
- [ ] 增强用户反馈（显示厂商/模型/端点）
- [ ] 添加异常处理和调试输出
- [ ] 编译检查
- [ ] lints 检查
- [ ] 测试场景 1-3

---

**下一步**：实施代码修改

