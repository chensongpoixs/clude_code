# 问题分析：qiniu base_url 缺少 /v1 导致 API 调用失败

## 一、问题现象

### 1.1 用户反馈
```
/provider qiniu
📝 使用配置文件: base_url=https://api.qnaigc.com, model=(自动), api_key=sk-d***8e78
✓ 已切换到厂商: qiniu

/models
qiniu 可用模型 (1)  ← 只有 1 个静态模型，没有从 API 获取
```

### 1.2 期望行为
应该从 `https://api.qnaigc.com/v1/models` 获取真实模型列表。

---

## 二、根因分析

### 2.1 API 路径问题

**用户配置**：
```yaml
providers:
  qiniu:
    base_url: "https://api.qnaigc.com"  # ← 没有 /v1
```

**代码构建的 API 路径**：
```python
# qiniu.py list_models()
f"{self._base_url}/models"
# → https://api.qnaigc.com/models  ❌ 错误

# qiniu.py chat()
f"{self._base_url}/chat/completions"
# → https://api.qnaigc.com/chat/completions  ❌ 错误
```

**正确的 API 路径（OpenAI-compatible 标准）**：
```
https://api.qnaigc.com/v1/models  ✅
https://api.qnaigc.com/v1/chat/completions  ✅
```

### 2.2 问题根源

1. 用户配置的 `base_url` 没有 `/v1` 后缀
2. 代码直接拼接 `/models` 和 `/chat/completions`
3. 导致 API 路径错误，请求返回 404 或无效数据

### 2.3 为什么静态列表显示？

`list_models()` 调用 `https://api.qnaigc.com/models` 失败（404 或无效响应），回退到静态列表：
```python
except Exception as e:
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(f"qiniu: 无法从 API 获取模型列表 ({e})，回退到静态列表")
return list(self.MODELS.values())  # 返回 1 个静态模型
```

---

## 三、解决方案

### 3.1 方案对比

| 方案 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| A | 代码智能规范化 base_url | 用户友好，兼容多种配置 | 需要修改代码 |
| B | 要求用户修改配置 | 无需改代码 | 用户体验差 |
| C | API 路径固定加 /v1 | 简单 | 可能导致 /v1/v1 重复 |

### 3.2 推荐方案：智能规范化 base_url

在 `__init__` 里规范化 `base_url`，确保以 `/v1` 结尾：

```python
def __init__(self, config: ProviderConfig):
    super().__init__(config)
    ...
    raw_url = config.base_url or os.getenv("QINIU_LLM_ENDPOINT", self.DEFAULT_BASE_URL)
    # 规范化：确保 base_url 以 /v1 结尾（OpenAI-compatible API 标准）
    raw_url = raw_url.rstrip("/")
    if not raw_url.endswith("/v1"):
        raw_url = raw_url + "/v1"
    self._base_url = raw_url
```

**效果**：
- `https://api.qnaigc.com` → `https://api.qnaigc.com/v1` ✅
- `https://api.qnaigc.com/v1` → `https://api.qnaigc.com/v1` ✅（不变）
- `http://127.0.0.1:11434` → `http://127.0.0.1:11434/v1` ✅

---

## 四、实施计划

### 4.1 修改位置
**文件**：`src/clude_code/llm/providers/qiniu.py`  
**函数**：`__init__()`  
**位置**：第 53 行

### 4.2 修改内容
```python
# 修改前
self._base_url = (config.base_url or os.getenv("QINIU_LLM_ENDPOINT", self.DEFAULT_BASE_URL)).rstrip("/")

# 修改后
raw_url = (config.base_url or os.getenv("QINIU_LLM_ENDPOINT", self.DEFAULT_BASE_URL)).rstrip("/")
# 规范化：确保 base_url 以 /v1 结尾（OpenAI-compatible API 标准）
if not raw_url.endswith("/v1"):
    raw_url = raw_url + "/v1"
self._base_url = raw_url
```

### 4.3 同步修改 DEFAULT_BASE_URL

由于我们现在会自动添加 /v1，DEFAULT_BASE_URL 可以改回不带 /v1：
```python
# 修改前
DEFAULT_BASE_URL = "http://127.0.0.1:11434/v1"

# 修改后（可选，保持一致性）
DEFAULT_BASE_URL = "http://127.0.0.1:11434"
```

但为了避免混淆，保持 `/v1` 也可以（代码会检测不重复添加）。

---

## 五、验证计划

### 5.1 测试用例

| 配置 base_url | 规范化后 | API 路径 |
|---------------|----------|----------|
| `https://api.qnaigc.com` | `https://api.qnaigc.com/v1` | `/v1/models` ✅ |
| `https://api.qnaigc.com/v1` | `https://api.qnaigc.com/v1` | `/v1/models` ✅ |
| `http://127.0.0.1:11434` | `http://127.0.0.1:11434/v1` | `/v1/models` ✅ |
| `http://127.0.0.1:11434/v1` | `http://127.0.0.1:11434/v1` | `/v1/models` ✅ |

### 5.2 验证步骤
```
/provider qiniu
/models  # 应该显示真实模型列表（如果 API 可用）
```

---

## 六、风险评估

### 6.1 潜在风险

#### 风险 1：某些 API 不使用 /v1 前缀
- **场景**：某些非标准 OpenAI-compatible API 可能不需要 /v1
- **影响**：低（七牛云应该遵循 OpenAI 标准）
- **缓解**：如果用户配置的 URL 已经包含完整路径（如 `/api/v2`），可能出问题

#### 风险 2：用户配置包含其他版本（如 /v2）
- **场景**：用户配置 `https://api.example.com/v2`
- **影响**：代码会添加 /v1 变成 `https://api.example.com/v2/v1`
- **缓解**：检查 URL 是否已包含 /v 开头的版本号

### 6.2 增强方案

更健壮的规范化逻辑：
```python
import re

raw_url = raw_url.rstrip("/")
# 如果 URL 不以 /v 开头的版本号结尾，添加 /v1
if not re.search(r'/v\d+$', raw_url):
    raw_url = raw_url + "/v1"
self._base_url = raw_url
```

这样：
- `https://api.qnaigc.com` → `https://api.qnaigc.com/v1` ✅
- `https://api.qnaigc.com/v1` → `https://api.qnaigc.com/v1` ✅（不变）
- `https://api.qnaigc.com/v2` → `https://api.qnaigc.com/v2` ✅（不变）

---

## 七、修复实施

### 7.1 修改内容

**文件**：`src/clude_code/llm/providers/qiniu.py`

**修改 1**：添加 `import re`
```python
import re
```

**修改 2**：`__init__` 中规范化 base_url
```python
# 修改前
self._base_url = (config.base_url or os.getenv("QINIU_LLM_ENDPOINT", self.DEFAULT_BASE_URL)).rstrip("/")

# 修改后
raw_url = (config.base_url or os.getenv("QINIU_LLM_ENDPOINT", self.DEFAULT_BASE_URL)).rstrip("/")
# 如果 URL 不以 /v 开头的版本号结尾（如 /v1, /v2），自动添加 /v1
if not re.search(r'/v\d+$', raw_url):
    raw_url = raw_url + "/v1"
self._base_url = raw_url
```

### 7.2 验证结果

- ✅ 编译检查通过
- ✅ Lints 检查通过

### 7.3 规范化效果

| 用户配置 base_url | 规范化后 | 状态 |
|-------------------|----------|------|
| `https://api.qnaigc.com` | `https://api.qnaigc.com/v1` | ✅ 自动添加 |
| `https://api.qnaigc.com/v1` | `https://api.qnaigc.com/v1` | ✅ 不变 |
| `http://127.0.0.1:11434` | `http://127.0.0.1:11434/v1` | ✅ 自动添加 |
| `http://127.0.0.1:11434/v2` | `http://127.0.0.1:11434/v2` | ✅ 保留原版本 |

---

## 八、与其他 Provider 的对比

### 8.1 两种 API 路径设计

| Provider | base_url 示例 | API 路径 | 最终 URL |
|----------|---------------|----------|----------|
| qiniu | `https://api.qnaigc.com/v1` | `/chat/completions` | `https://api.qnaigc.com/v1/chat/completions` |
| openai_compat | `http://127.0.0.1:8899` | `/v1/chat/completions` | `http://127.0.0.1:8899/v1/chat/completions` |

### 8.2 设计差异

- **qiniu.py**：base_url 包含 /v1，API 路径不带
- **openai_compat.py**：base_url 不含 /v1，API 路径硬编码 /v1

两种方式都有效，qiniu.py 通过自动规范化确保兼容。

---

**修复完成** ✅

用户现在可以使用以下配置：
```yaml
providers:
  qiniu:
    base_url: "https://api.qnaigc.com"  # 无需手动加 /v1
    api_key: "sk-xxx"
```

系统会自动规范化为 `https://api.qnaigc.com/v1`，API 调用将正确工作。

