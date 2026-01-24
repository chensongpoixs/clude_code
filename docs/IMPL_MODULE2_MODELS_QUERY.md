# 模块 2 实施：增强模型列表查询

## 一、问题定位

### 1.1 需求分析
当用户执行 `/models` 命令时，应该：
1. 尝试从厂商真实 API 获取模型列表
2. 如果 API 调用失败，回退到静态硬编码列表
3. 显示模型来源（API 还是静态列表）
4. 合理的超时时间和错误处理

### 1.2 当前问题
查看 `qiniu.py` 的 `list_models()` 实现：

```python
def list_models(self) -> list[ModelInfo]:
    """返回静态模型列表（七牛云暂无公开模型列表API）"""
    return [
        ModelInfo(
            id="qiniu-llm-v1",
            description="七牛云大模型 v1",
            context_length=8192,
        )
    ]
```

**问题**：
- 硬编码返回 1 个模型
- 没有尝试调用 API
- 用户切换到 qiniu 后看不到真实可用模型

### 1.3 OpenAI-compatible API 标准
大部分厂商（qiniu, ollama, deepseek, openai）都支持：
```
GET {base_url}/models
```

响应格式：
```json
{
  "object": "list",
  "data": [
    {
      "id": "qwen2.5:latest",
      "object": "model",
      "created": 1234567890,
      "owned_by": "library"
    }
  ]
}
```

---

## 二、设计方案

### 2.1 核心逻辑

```
list_models():
  1. 尝试调用 {base_url}/models API
  2. 如果成功 → 解析响应，返回模型列表
  3. 如果失败 → 回退到静态列表
  4. 添加缓存（可选）避免频繁请求
```

### 2.2 实现细节

#### 步骤 1：HTTP 请求
使用 `httpx` 库（已经在项目中使用）：
```python
import httpx

def list_models(self) -> list[ModelInfo]:
    # 先尝试 API
    try:
        models = self._fetch_models_from_api()
        if models:
            return models
    except Exception as e:
        # 记录日志，回退静态列表
        pass
    
    # 回退静态列表
    return self._get_static_models()
```

#### 步骤 2：API 调用实现
```python
def _fetch_models_from_api(self) -> list[ModelInfo]:
    """从 API 获取模型列表"""
    base_url = self.config.base_url.rstrip("/")
    url = f"{base_url}/models"
    
    # 超时设置：5 秒（避免等太久）
    timeout = httpx.Timeout(5.0, connect=2.0)
    
    with httpx.Client(timeout=timeout) as client:
        resp = client.get(url)
        resp.raise_for_status()  # 4xx/5xx 抛异常
        
        data = resp.json()
        models = []
        
        # 解析 OpenAI-compatible 格式
        if "data" in data:
            for item in data["data"]:
                models.append(ModelInfo(
                    id=item.get("id", "unknown"),
                    description=item.get("description", ""),
                    context_length=item.get("context_length", 4096),
                ))
        
        return models
```

#### 步骤 3：静态列表回退
```python
def _get_static_models(self) -> list[ModelInfo]:
    """回退：返回静态模型列表"""
    return [
        ModelInfo(
            id="qiniu-llm-v1",
            description="七牛云大模型 v1（静态列表）",
            context_length=8192,
        )
    ]
```

### 2.3 缓存设计（可选）

为了避免频繁调用 API，可以添加简单缓存：
```python
class QiniuProvider(LLMProvider):
    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self._models_cache = None  # 缓存
        self._cache_time = None    # 缓存时间
        self._cache_ttl = 300      # 5 分钟
    
    def list_models(self) -> list[ModelInfo]:
        # 检查缓存
        if self._is_cache_valid():
            return self._models_cache
        
        # 获取模型
        models = self._fetch_or_fallback()
        
        # 更新缓存
        self._models_cache = models
        self._cache_time = time.time()
        
        return models
```

**是否需要缓存？**
- **优点**：减少 API 调用，提升响应速度
- **缺点**：增加代码复杂度，可能显示过期数据
- **建议**：先不加缓存，等用户反馈性能问题再加

---

## 三、实施步骤

### 3.1 修改 `qiniu.py`

#### 位置
文件：`src/clude_code/llm/providers/qiniu.py`  
函数：`list_models()`

#### 修改内容
```python
def list_models(self) -> list[ModelInfo]:
    """获取模型列表（先尝试 API，失败则回退静态列表）"""
    try:
        return self._fetch_models_from_api()
    except Exception as e:
        # API 调用失败，回退静态列表
        return self._get_static_models()

def _fetch_models_from_api(self) -> list[ModelInfo]:
    """从 {base_url}/models API 获取模型列表"""
    import httpx
    
    base_url = self.config.base_url.rstrip("/")
    url = f"{base_url}/models"
    
    timeout = httpx.Timeout(5.0, connect=2.0)
    
    with httpx.Client(timeout=timeout) as client:
        resp = client.get(url)
        resp.raise_for_status()
        
        data = resp.json()
        models = []
        
        if "data" in data and isinstance(data["data"], list):
            for item in data["data"]:
                models.append(ModelInfo(
                    id=item.get("id", "unknown"),
                    description=item.get("description", ""),
                    context_length=item.get("context_length", 4096),
                ))
        
        if not models:
            # API 返回空列表，回退静态列表
            raise ValueError("API 返回空模型列表")
        
        return models

def _get_static_models(self) -> list[ModelInfo]:
    """回退：静态模型列表"""
    return [
        ModelInfo(
            id="qiniu-llm-v1",
            description="七牛云大模型 v1（静态列表）",
            context_length=8192,
        )
    ]
```

### 3.2 通用化：提取到 OpenAICompatProvider

#### 问题
qiniu, ollama, deepseek 等厂商都需要同样的逻辑，应该提取到公共基类。

#### 方案
在 `openai_compat.py` 里实现通用的 `list_models()`：

```python
class OpenAICompatProvider(LLMProvider):
    """OpenAI-compatible provider 的通用基类"""
    
    def list_models(self) -> list[ModelInfo]:
        """通用实现：先尝试 API，失败则回退静态列表"""
        try:
            return self._fetch_models_from_api()
        except Exception:
            return self._get_static_models()
    
    def _fetch_models_from_api(self) -> list[ModelInfo]:
        """从 {base_url}/models 获取模型"""
        import httpx
        
        base_url = self.config.base_url.rstrip("/")
        url = f"{base_url}/models"
        timeout = httpx.Timeout(5.0, connect=2.0)
        
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(url)
            resp.raise_for_status()
            data = resp.json()
            
            models = []
            if "data" in data and isinstance(data["data"], list):
                for item in data["data"]:
                    models.append(ModelInfo(
                        id=item.get("id", "unknown"),
                        description=item.get("description", ""),
                        context_length=item.get("context_length", 4096),
                    ))
            
            if not models:
                raise ValueError("API 返回空模型列表")
            
            return models
    
    def _get_static_models(self) -> list[ModelInfo]:
        """子类需要重写这个方法"""
        raise NotImplementedError("子类需要提供静态模型列表")
```

然后 `QiniuProvider` 只需要：
```python
class QiniuProvider(OpenAICompatProvider):
    def _get_static_models(self) -> list[ModelInfo]:
        return [
            ModelInfo(
                id="qiniu-llm-v1",
                description="七牛云大模型 v1（静态列表）",
                context_length=8192,
            )
        ]
```

**是否需要通用化？**
- **优点**：代码复用，多个 provider 受益
- **缺点**：增加复杂度，可能影响其他 provider
- **建议**：先只改 `qiniu.py`，等验证通过后再考虑通用化

---

## 四、异常处理设计

### 4.1 场景 1：网络错误
```python
try:
    resp = client.get(url)
except httpx.ConnectError:
    # 无法连接到服务器
    return self._get_static_models()
except httpx.TimeoutException:
    # 超时
    return self._get_static_models()
```

### 4.2 场景 2：HTTP 错误
```python
try:
    resp.raise_for_status()
except httpx.HTTPStatusError as e:
    # 404/500 等错误
    return self._get_static_models()
```

### 4.3 场景 3：响应格式错误
```python
try:
    data = resp.json()
except (ValueError, KeyError):
    # JSON 解析失败或格式不对
    return self._get_static_models()
```

### 4.4 统一异常处理
```python
def list_models(self) -> list[ModelInfo]:
    try:
        return self._fetch_models_from_api()
    except Exception as e:
        # 所有异常都回退静态列表
        # 可选：记录调试日志
        return self._get_static_models()
```

---

## 五、用户反馈设计

### 5.1 显示模型来源

#### 方案 1：在 ModelInfo 里添加 source 字段
```python
@dataclass
class ModelInfo:
    id: str
    description: str = ""
    context_length: int = 4096
    source: str = "api"  # "api" 或 "static"
```

**缺点**：需要修改数据类，影响面大

#### 方案 2：在 `/models` 命令里显示
```python
# slash_commands.py::_models()
models = mm.list_models()
ctx.console.print(f"[bold]可用模型（{len(models)} 个）：[/bold]")

# 检测是否是静态列表（简单判断）
if len(models) == 1 and "(静态列表)" in models[0].description:
    ctx.console.print("[dim]⚠ 无法连接到厂商 API，显示静态列表[/dim]")
```

**建议**：使用方案 2，避免修改数据结构

### 5.2 显示详细错误（debug 模式）

在 `_fetch_models_from_api()` 里：
```python
except Exception as e:
    if DEBUG:  # 或者通过 logger
        print(f"DEBUG: API 调用失败: {e}")
    raise  # 重新抛出，让 list_models() 回退
```

---

## 六、测试计划

### 6.1 测试场景 1：本地有 ollama 服务
**前置条件**：
```bash
# 启动 ollama
ollama serve
```

**配置**：
```yaml
providers:
  qiniu:
    base_url: "http://127.0.0.1:11434/v1"
```

**操作**：
```
/provider qiniu
/models
```

**期望**：
- 显示 ollama 的真实模型列表（多个模型）
- 不显示 "(静态列表)" 标记

### 6.2 测试场景 2：本地无服务
**前置条件**：关闭 ollama

**操作**：
```
/provider qiniu
/models
```

**期望**：
- 显示静态列表（1 个模型）
- 模型 description 包含 "(静态列表)"
- 可选：显示 "⚠ 无法连接到厂商 API"

### 6.3 测试场景 3：真实七牛云 API
**配置**：
```yaml
providers:
  qiniu:
    base_url: "https://api.qnaigc.com/v1"
    api_key: "sk-real-key"
```

**操作**：
```
/provider qiniu
/models
```

**期望**：
- 如果七牛云支持 `/models` API → 显示真实模型
- 如果不支持 → 返回 404 → 回退静态列表

### 6.4 测试场景 4：超时
**配置**：
```yaml
providers:
  qiniu:
    base_url: "http://10.255.255.1:11434/v1"  # 不存在的 IP
```

**操作**：
```
/provider qiniu
/models
```

**期望**：
- 5 秒超时后回退静态列表
- 不卡死

---

## 七、实施检查清单

### 7.1 代码修改
- [ ] 修改 `qiniu.py::list_models()`
- [ ] 添加 `_fetch_models_from_api()`
- [ ] 添加 `_get_static_models()`
- [ ] 统一异常处理
- [ ] 设置合理超时时间（5 秒）

### 7.2 代码质量
- [ ] 编译检查
- [ ] lints 检查
- [ ] 异常处理完整
- [ ] 空值/边界检查

### 7.3 测试验证
- [ ] 场景 1：有服务
- [ ] 场景 2：无服务
- [ ] 场景 3：真实 API
- [ ] 场景 4：超时

---

## 八、健壮性考虑

### 8.1 空响应
```python
if not models:
    raise ValueError("API 返回空模型列表")
```

### 8.2 格式异常
```python
if "data" in data and isinstance(data["data"], list):
    # 确保 data 是列表
```

### 8.3 超时控制
```python
timeout = httpx.Timeout(5.0, connect=2.0)
# 连接超时 2 秒，总超时 5 秒
```

### 8.4 回退保证
```python
def list_models(self) -> list[ModelInfo]:
    try:
        return self._fetch_models_from_api()
    except Exception:
        return self._get_static_models()
    # 保证一定返回模型列表，不会抛异常
```

---

## 九、实施优先级

### P1（本次实施）
- ✅ 修改 `qiniu.py::list_models()`
- ✅ 添加 API 调用逻辑
- ✅ 异常处理和回退

### P2（后续优化）
- ⏸ 提取到 `OpenAICompatProvider`（通用化）
- ⏸ 添加缓存机制
- ⏸ 添加详细的调试日志

---

**下一步**：实施代码修改，先只改 `qiniu.py`

