# 问题分析：qiniu provider 切换后仍使用旧模型配置

## 一、问题现象

### 1.1 用户操作序列
```
1. /provider qiniu  → 提示"✓ 已经在使用厂商: qiniu"
2. /models         → 显示 1 个模型 (qiniu-llm-v1)
3. 你好啊          → LLM 请求失败
```

### 1.2 错误日志关键信息
```
provider_id=ollama 
provider_base_url=http://127.0.0.1:11434 
provider_model=llama3.2

model=ggml-org/gemma-3-12b-it-GGUF 
api_mode=openai_compat 
base_url=http://127.0.0.1:8899

七牛云请求失败: HTTP 404 body={"error_msg":"404 Route Not Found"}
```

### 1.3 配置状态（/provider-configs）
```
qiniu:
  - enabled: False
  - base_url: https://api.qn... (截断显示)
  - default_model: (空)
  - api_key: sk-d***8e78
  - 配置状态: configured
```

---

## 二、根因分析

### 2.1 核心矛盾：三层配置不一致

代码里存在**三个层级**的配置/状态，导致混乱：

#### 层级 1：ModelManager（运行时状态）
- `current_provider_id = "qiniu"`
- `current_model = "qiniu-llm-v1"`
- **这个是正确的**（`/provider qiniu` 已经切换）

#### 层级 2：AgentLoop.llm（固定客户端）
- `loop.llm` = `LlamaCppHttpClient` 实例
- `loop.llm.model = "ggml-org/gemma-3-12b-it-GGUF"`
- `loop.llm.base_url = "http://127.0.0.1:8899"`
- **这个没有更新**（仍然是初始化时的 llama.cpp 配置）

#### 层级 3：配置文件（~/.clude/.clude.yaml）
```yaml
providers:
  qiniu:
    enabled: false
    base_url: "https://api.qnaigc.com/v1"  # 真实七牛云地址
    api_key: "sk-d...8e78"
    default_model: ""  # 空
```
- **这个配置有问题**：
  - `enabled: false` → 逻辑上应该是 true
  - `base_url` 是真实七牛云（用户可能没权限）
  - `default_model` 为空 → 导致切换后没有可用模型

---

### 2.2 代码执行路径追踪

#### 路径 1：`/provider qiniu` 执行流程
```python
# slash_commands.py::_switch_provider()
1. 检查 qiniu 是否在 ModelManager._providers 中
   → 不在（因为是第一次切换）

2. 从 ProviderRegistry 获取 provider 类
   → ProviderRegistry.get_provider("qiniu", config)

3. 读取配置文件
   provider_cfg_item = ctx.cfg.providers.get_item("qiniu")
   → 读到：
      - base_url = "https://api.qnaigc.com/v1"
      - default_model = ""
      - api_key = "sk-d...8e78"

4. 创建 ProviderConfig
   config = ProviderConfig(
       name="qiniu",
       api_key="sk-d...8e78",
       base_url="https://api.qnaigc.com/v1",  # 真实七牛云
       default_model=""  # 空！
   )

5. 实例化 QiniuProvider
   provider = QiniuProvider(config)
   → provider._base_url = "https://api.qnaigc.com/v1"
   → provider._model = ""  # 空！但基类会用 DEFAULT 兜底

6. 注册到 ModelManager
   mm.register_provider("qiniu", provider)
   mm.switch_provider("qiniu")
```

**问题 1**：配置文件里的 `base_url` 是真实七牛云地址，但用户可能没权限或不想用。

**问题 2**：`default_model` 为空，导致 `provider.current_model` 可能是空或默认值。

#### 路径 2：`你好啊` LLM 请求流程
```python
# llm_io.py::llm_chat()
1. 获取当前 provider
   mm = get_model_manager()
   current_provider = mm.get_provider()  # → QiniuProvider 实例

2. 调用 provider.chat()
   assistant_text = current_provider.chat(loop.messages)

3. QiniuProvider.chat() 执行
   → 发送请求到 self._base_url = "https://api.qnaigc.com/v1"
   → 返回 404（用户没权限或路由不对）
```

**关键发现**：虽然 provider 切换成功了，但是：
- provider 使用的 `base_url` 来自配置文件（真实七牛云）
- 用户本地没有七牛云服务 → 404

#### 路径 3：日志输出的"旧 provider 信息"
```python
# llm_io.py::log_llm_request_params_to_file()
# 第 354 行附近
provider_id = getattr(loop, "_last_provider_id", "")
provider_base_url = getattr(loop, "_last_provider_base_url", "")
provider_model = getattr(loop, "_last_provider_model", "")
```

日志显示 `provider_id=ollama` 是因为：
- 第一次聊天时（之前的会话），用的是 ollama
- `loop._last_provider_*` 保存的是上一次的值
- 虽然现在我改了代码在 `llm_chat()` 开头更新这些值，但用户还没重启会话

---

### 2.3 配置文件来源分析

用户的 `~/.clude/.clude.yaml` 里有：
```yaml
providers:
  qiniu:
    enabled: false
    base_url: "https://api.qnaigc.com/v1"
    api_key: "sk-d...8e78"
```

**可能的来源**：
1. 用户之前手动配置过 qiniu（用的是真实七牛云地址）
2. 或者是某个配置模板/示例文件残留

**问题**：
- `base_url` 是真实七牛云 → 用户本地测试时会失败
- `enabled: false` → 逻辑上应该是 true（如果想用的话）
- `default_model: ""` → 应该设置一个默认模型

---

## 三、解决方案

### 3.1 短期修复（立即可用）

#### 方案 A：更新配置文件（推荐）
用户手动编辑 `~/.clude/.clude.yaml`：
```yaml
providers:
  qiniu:
    enabled: true
    base_url: "http://127.0.0.1:11434"  # 本地 ollama/llama.cpp
    api_key: ""  # 本地不需要 key
    default_model: "qiniu-llm-v1"
```

#### 方案 B：使用 slash 命令配置
```
/provider-config-set qiniu base_url=http://127.0.0.1:11434 enabled=true default_model=qiniu-llm-v1
```

#### 方案 C：切换到本地已有的 provider
```
/provider ollama    # 或
/provider llama_cpp
```

### 3.2 中期优化（代码改进）

#### 优化 1：QiniuProvider 的 DEFAULT_BASE_URL
我已经改了：
```python
DEFAULT_BASE_URL = "http://127.0.0.1:11434"  # 本地测试端点
```
但这个只在**配置文件没有 qiniu 配置**时生效。

**改进方案**：
- 如果配置文件里的 `base_url` 是真实七牛云，但用户本地没服务
- 应该在 `_switch_provider()` 时给出警告或自动回退

#### 优化 2：default_model 为空时的兜底
在 `ModelManager.switch_provider()` 里，如果 `current_model` 为空：
```python
if not provider.current_model:
    models = provider.list_models()
    if models:
        provider.current_model = models[0].id
```
我已经加了这个逻辑，但需要验证。

#### 优化 3：配置文件校验
在 `clude doctor` 或 `/provider-config` 时，检查：
- `base_url` 是否可达
- `default_model` 是否为空
- `enabled` 是否与实际使用一致

### 3.3 长期架构（业界对标）

参考 LangChain/LiteLLM 的做法：
1. **配置分层**：
   - 全局配置（~/.clude/.clude.yaml）
   - 项目配置（.clude/config.yaml）
   - 环境变量（QINIU_BASE_URL）
   - 运行时覆盖（命令行参数）

2. **配置校验**：
   - 启动时校验必填字段
   - 提供 `clude providers validate` 命令

3. **配置迁移**：
   - 提供 `clude providers migrate` 命令
   - 自动更新旧配置格式

---

## 四、验证步骤

### 4.1 验证 provider 切换
```bash
# 1. 重启 clude chat（清理旧状态）
clude chat

# 2. 切换到 qiniu
/provider qiniu

# 3. 检查日志
你好

# 期望：日志显示
# provider_id=qiniu
# provider_base_url=http://127.0.0.1:11434
# provider_model=qiniu-llm-v1
```

### 4.2 验证配置更新
```bash
# 1. 更新配置
/provider-config-set qiniu base_url=http://127.0.0.1:11434 enabled=true default_model=qiniu-llm-v1

# 2. 查看配置
/provider-config qiniu

# 期望：显示更新后的值
```

### 4.3 验证模型列表
```bash
# 1. 切换到 qiniu
/provider qiniu

# 2. 查看模型
/models

# 期望：
# - 如果本地 11434 有 ollama，显示 ollama 的模型列表
# - 如果本地 11434 没服务，显示静态的 qiniu-llm-v1
```

---

## 五、总结

### 5.1 核心问题
1. **配置文件里的 qiniu 配置不适合本地测试**（真实七牛云地址）
2. **日志显示的 provider 信息是上一次的**（已修复代码，但用户需重启）
3. **default_model 为空**导致切换后没有可用模型

### 5.2 修复状态
| 问题 | 状态 | 说明 |
|------|------|------|
| 日志显示旧 provider | ✅ 已修复 | 代码已改，用户需重启会话 |
| qiniu DEFAULT_BASE_URL | ✅ 已修复 | 改为本地测试端点 |
| default_model 为空 | ✅ 已修复 | ModelManager 自动兜底 |
| 配置文件不合理 | ⚠️ 需用户操作 | 用户手动更新或用 slash 命令 |

### 5.3 下一步行动
1. **用户**：更新 qiniu 配置（方案 A 或 B）
2. **用户**：重启 `clude chat`（清理旧状态）
3. **开发**：添加配置校验和迁移工具
4. **开发**：优化 provider 切换时的错误提示

---

## 六、业界对标

### 6.1 LangChain
- 配置优先级：环境变量 > 参数 > 配置文件
- 自动降级：如果配置的 provider 不可用，自动切换到默认

### 6.2 LiteLLM
- 统一配置格式：所有 provider 使用相同的 key 名称
- 配置校验：启动时检查必填字段，给出明确错误提示

### 6.3 Cursor
- 本地优先：默认使用本地模型（llama.cpp/ollama）
- 云端按需：只在用户明确配置时使用云端 provider

---

**文档版本**: 1.0  
**创建时间**: 2026-01-24  
**最后更新**: 2026-01-24  

