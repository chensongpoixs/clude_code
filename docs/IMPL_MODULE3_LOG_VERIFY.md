# 模块 3 实施：日志信息同步验证

## 一、问题定位

### 1.1 需求分析
当用户执行 `/provider qiniu` 切换厂商后，下一次 LLM 请求的日志应该显示：
1. 正确的 `provider_id`（qiniu，而不是旧的 ollama）
2. 正确的 `base_url`（qiniu 配置的地址，而不是旧的 llama.cpp 地址）
3. 正确的 `model`（qiniu 的模型，而不是旧的 gemma 模型）

### 1.2 历史问题
之前的问题是：
```
[日志]
provider_id=ollama     ← 应该是 qiniu
base_url=http://127.0.0.1:8899  ← 应该是 qiniu 的地址
model=gemma3.2:2b      ← 应该是 qiniu 的模型
```

这是因为日志记录的时机不对，在实际 LLM 调用之前就已经记录了旧的 provider 信息。

### 1.3 当前状态
根据之前的修复（模块 1），`llm_io.py` 的 `llm_chat()` 函数应该已经在正确的时机获取 provider 信息。

**需要验证**：
1. 日志记录时机是否正确
2. 所有代码路径是否都覆盖
3. 多轮对话后是否仍然正确

---

## 二、代码审查

### 2.1 核心代码位置
文件：`src/clude_code/orchestrator/agent_loop/llm_io.py`  
函数：`llm_chat()`

### 2.2 需要检查的点

#### 检查点 1：provider 信息获取时机
```python
# 应该在 llm_chat() 开头获取当前 provider
def llm_chat(loop, messages, ...):
    # 获取当前 provider（在这里，确保获取的是最新的）
    from ...llm.model_manager import ModelManager
    mm = ModelManager()
    current_provider = mm.get_provider()
    provider_id = mm.get_current_provider_id()
    current_model = mm.get_current_model()
```

#### 检查点 2：日志记录是否使用正确的 provider 信息
```python
# 日志记录应该使用上面获取的信息
log_llm_request_params_to_file(
    provider_id=provider_id,  # ← 这里应该是动态获取的
    base_url=current_provider.config.base_url,  # ← 这里应该是动态获取的
    model=current_model,  # ← 这里应该是动态获取的
    ...
)
```

#### 检查点 3：实际 LLM 调用是否使用正确的 provider
```python
# 实际调用应该走 current_provider.chat()
response = current_provider.chat(messages, model=current_model, ...)
```

---

## 三、实施步骤

### 3.1 第一步：阅读 llm_io.py 代码
读取 `llm_chat()` 函数的完整实现，确认：
1. provider 信息在哪里获取
2. 日志在哪里记录
3. 实际 LLM 调用在哪里

### 3.2 第二步：检查 provider 信息获取时机
确认 `provider_id`, `base_url`, `model` 是在 `llm_chat()` 开头获取的，而不是从 `loop` 对象或旧的配置中获取的。

### 3.3 第三步：检查日志记录
确认 `log_llm_request_params_to_file()` 使用的是动态获取的 provider 信息。

### 3.4 第四步：检查实际 LLM 调用
确认 `current_provider.chat()` 被调用，而不是旧的 `loop.llm.chat()`。

### 3.5 第五步：添加调试日志（如果需要）
如果发现问题，添加调试日志帮助排查。

---

## 四、验证方案

### 4.1 场景 1：切换后首次对话
**操作**：
```
/provider qiniu
你好
```

**预期日志**：
```
===== LLM Request Params =====
provider_id: qiniu
base_url: http://127.0.0.1:11434  (或配置的地址)
model: qiniu-llm-v1
```

### 4.2 场景 2：多轮对话
**操作**：
```
/provider qiniu
你好
你好啊
请帮我写代码
```

**预期**：每次日志都显示 `provider_id: qiniu`

### 4.3 场景 3：多次切换
**操作**：
```
/provider qiniu
你好
/provider openai
你好
/provider qiniu
你好
```

**预期**：
- 第一次对话：`provider_id: qiniu`
- 第二次对话：`provider_id: openai`
- 第三次对话：`provider_id: qiniu`

---

## 五、实施检查清单

### 5.1 代码审查
- [ ] 阅读 `llm_io.py::llm_chat()` 完整代码
- [ ] 确认 provider 信息获取时机
- [ ] 确认日志记录使用正确的信息
- [ ] 确认实际 LLM 调用使用正确的 provider

### 5.2 问题修复（如果需要）
- [ ] 修正 provider 信息获取时机
- [ ] 修正日志记录参数
- [ ] 添加调试日志

### 5.3 验证
- [ ] 编译检查
- [ ] lints 检查
- [ ] 功能测试（可选，取决于是否能运行）

---

## 六、健壮性考虑

### 6.1 provider 可能为空
```python
current_provider = mm.get_provider()
if current_provider is None:
    # 回退到默认 provider 或报错
```

### 6.2 base_url 可能缺失
```python
base_url = (
    getattr(current_provider.config, "base_url", None)
    or "(未配置)"
)
```

### 6.3 model 可能为空
```python
model = mm.get_current_model() or "(未设置)"
```

---

## 七、代码审查结果

### 7.1 审查发现

#### 发现 1：provider 信息获取时机正确 ✅
**位置**：第 156-172 行
```python
# 提前记录 provider 信息（用于日志输出正确的当前 provider，避免拿到上一次的）
try:
    from clude_code.llm import get_model_manager
    mm = get_model_manager()
    current_provider = mm.get_provider()
    if current_provider:
        loop._last_provider_id = mm.get_current_provider_id()
        loop._last_provider_base_url = ...
        loop._last_provider_model = current_provider.current_model
```
✅ **正确**：在 LLM 调用前获取 provider 信息

#### 发现 2：实际 LLM 调用正确 ✅
**位置**：第 240-262 行
```python
provider = mm.get_provider()
if provider is not None:
    used_provider_id = mm.get_current_provider_id()
    ...
    assistant_text = provider.chat(...)  # ← 使用当前 provider
else:
    assistant_text = loop.llm.chat(loop.messages)  # ← 回退
```
✅ **正确**：优先使用 `provider.chat()`

#### 发现 3：日志记录使用错误的变量 ❌
**位置**：`log_llm_request_params_to_file()` 第 407-409 行
```python
pid = getattr(loop, "_active_provider_id", None)  # ← 错误！
purl = getattr(loop, "_active_provider_base_url", None)
pmodel = getattr(loop, "_active_provider_model", None)
```

**问题分析**：
1. `_active_provider_id` 是在 **LLM 调用之后** 设置的（第 268 行）
2. `log_llm_request_params_to_file()` 是在 **LLM 调用之前** 调用的（第 225 行）
3. 所以日志打印时 `_active_provider_id` 是上一次的值或 None

**应该使用**：`_last_provider_id`（第 162 行设置，在日志打印前）

### 7.2 修复方案

**修改 `log_llm_request_params_to_file()` 第 407-409 行**：
```python
# 修改前
pid = getattr(loop, "_active_provider_id", None)
purl = getattr(loop, "_active_provider_base_url", None)
pmodel = getattr(loop, "_active_provider_model", None)

# 修改后
pid = getattr(loop, "_last_provider_id", None)
purl = getattr(loop, "_last_provider_base_url", None)
pmodel = getattr(loop, "_last_provider_model", None)
```

**理由**：
- `_last_provider_*` 在第 162-164 行设置（LLM 调用前）
- `_active_provider_*` 在第 268-270 行设置（LLM 调用后）
- 日志是在 LLM 调用前打印的（第 225 行）
- 所以应该用 `_last_provider_*`

---

## 八、实施修复

**文件**：`src/clude_code/orchestrator/agent_loop/llm_io.py`  
**位置**：`log_llm_request_params_to_file()` 函数，第 407-409 行

---

**下一步**：执行代码修复

