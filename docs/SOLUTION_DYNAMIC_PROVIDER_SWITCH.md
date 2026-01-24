# 动态厂商切换增强方案

## 问题重述
用户需求：**会话中随时 `/provider xxx` 切换厂家，无需改配置文件**。

当前问题：
1. 配置文件里有旧的 qiniu 配置（真实七牛云地址）→ 切换时会用这个地址 → 失败
2. 每个厂家都需要配置 base_url/api_key → 无法快速测试切换

## 解决方案

### 方案 1：智能配置回退（推荐）

#### 1.1 设计思路
- 如果配置文件里有厂商配置 → 优先使用
- 如果配置不合理（如 base_url 是远程地址但没有 api_key）→ **降级到测试配置**
- 测试配置：使用本地端点（如 `http://127.0.0.1:11434`）

#### 1.2 实现逻辑
```python
# slash_commands.py::_switch_provider()

def _get_effective_config(provider_id: str, registry_config: ProviderConfig) -> ProviderConfig:
    """
    智能配置合并：
    1. 读取配置文件
    2. 如果配置文件里的 base_url 是远程地址（https://）但没有 api_key → 降级
    3. 降级策略：使用本地测试端点
    """
    file_config = ctx.cfg.providers.get_item(provider_id)
    
    if file_config:
        base_url = file_config.base_url or ""
        api_key = file_config.api_key or ""
        
        # 检测：远程地址但没有 api_key → 不合理
        if base_url.startswith("https://") and not api_key:
            console.print(f"[yellow]⚠ 检测到 {provider_id} 配置了远程地址但无 API key，将使用本地测试配置[/yellow]")
            # 降级到本地测试配置
            return ProviderConfig(
                name=provider_id,
                base_url="http://127.0.0.1:11434",  # 本地 ollama/llama.cpp
                default_model=file_config.default_model or registry_config.default_model
            )
        
        # 配置合理，直接使用
        return file_config
    
    # 没有配置，使用默认测试配置
    return ProviderConfig(
        name=provider_id,
        base_url="http://127.0.0.1:11434",
        default_model=registry_config.default_model
    )
```

#### 1.3 用户体验
```bash
# 场景 1：配置文件没有 qiniu 配置
/provider qiniu
# → 自动使用本地测试配置 (http://127.0.0.1:11434)
# → 提示："使用本地测试配置，如需使用真实七牛云请运行 /provider-config-set qiniu ..."

# 场景 2：配置文件有 qiniu 但是远程地址+无 api_key
/provider qiniu
# → 检测到配置不合理
# → 提示："检测到远程地址但无 API key，已降级到本地测试配置"
# → 自动使用 http://127.0.0.1:11434

# 场景 3：配置文件有完整配置（base_url + api_key）
/provider qiniu
# → 使用配置文件的配置
# → 正常调用真实七牛云
```

---

### 方案 2：provider 类型分类

#### 2.1 设计思路
将 provider 分为三类：
1. **local**（本地）：llama_cpp, ollama, localai 等 → 默认 `http://127.0.0.1:xxxx`
2. **cloud**（云端）：openai, anthropic, qiniu 等 → 必须配置 api_key
3. **test**（测试）：任何 cloud provider 都可以用本地端点测试

#### 2.2 实现
```python
class QiniuProvider(LLMProvider):
    PROVIDER_TYPE = "cloud"  # 标记为云端
    SUPPORT_LOCAL_TEST = True  # 支持本地测试
    
    def __init__(self, config: ProviderConfig):
        # 如果是本地测试模式
        if config.base_url and config.base_url.startswith("http://127.0.0.1"):
            self._test_mode = True
            # 本地测试：不需要 api_key
        else:
            self._test_mode = False
            # 云端模式：需要 api_key
            if not config.api_key:
                raise ValueError(f"{self.PROVIDER_NAME} 云端模式需要 api_key")
```

#### 2.3 用户体验
```bash
# 本地测试模式
/provider qiniu
# → 提示："qiniu 云端厂商，当前使用本地测试模式"
# → base_url = http://127.0.0.1:11434

# 切换到云端模式
/provider-config-set qiniu base_url=https://api.qnaigc.com/v1 api_key=sk-xxx
/provider qiniu
# → 提示："qiniu 已切换到云端模式"
```

---

### 方案 3：临时配置覆盖（最灵活）

#### 3.1 设计思路
- 配置文件是"持久配置"
- 会话中的 `/provider-config-set` 是"临时配置"（不写入文件）
- 支持 `--temp` 参数

#### 3.2 实现
```bash
# 临时配置（不写入文件）
/provider-config-set qiniu base_url=http://127.0.0.1:11434 --temp

# 永久配置（写入文件）
/provider-config-set qiniu base_url=http://127.0.0.1:11434
```

---

## 推荐实现顺序

### 阶段 1：快速修复（立即可用）
**目标**：让用户能快速切换厂家测试，无需配置

**实现**：
1. 修改 `_switch_provider()`：
   - 检测配置文件的 base_url 是否合理
   - 如果是远程地址但没有 api_key → 提示并降级到本地
2. 修改所有 cloud provider 的默认行为：
   - 如果 base_url 是本地地址 → 跳过 api_key 校验

**代码改动**：
- `src/clude_code/cli/slash_commands.py::_switch_provider()`
- `src/clude_code/llm/base.py::LLMProvider.__init__()`

### 阶段 2：模型列表增强
**目标**：`/models` 显示厂家真实模型列表

**实现**：
1. 为每个 provider 实现 `list_models()` 的真实 API 调用
2. qiniu: `GET {base_url}/models`（OpenAI-compatible）
3. 如果 API 调用失败 → 回退到静态列表

**代码改动**：
- `src/clude_code/llm/providers/qiniu.py::list_models()`
- 其他 cloud providers 类似

### 阶段 3：配置管理优化
**目标**：更好的配置体验

**实现**：
1. 支持临时配置（`--temp`）
2. 配置校验（`clude providers validate`）
3. 配置模板（`clude providers init <provider>`）

---

## 立即可操作的方案

### 选项 A：删除配置文件里的 qiniu 配置（最简单）
编辑 `~/.clude/.clude.yaml`，**删除或注释掉** qiniu 部分：
```yaml
providers:
  openai:
    enabled: true
    base_url: "https://api.openai.com/v1"
    api_key: "sk-t...7890"
  # qiniu:  # 注释掉
  #   enabled: false
  #   base_url: "https://api.qnaigc.com/v1"
```

然后：
```bash
# 重启 clude chat
clude chat

# 切换到 qiniu（会使用默认本地配置）
/provider qiniu

# 查看模型
/models
```

### 选项 B：我现在就改代码（推荐）
让我立即实现"智能配置回退"逻辑，这样你：
- 不需要删除配置文件
- 不需要手动配置每个厂家
- 可以随时切换任意厂家测试

需要吗？我可以立即开始改。

