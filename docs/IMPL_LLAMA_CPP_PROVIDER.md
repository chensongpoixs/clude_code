# llama.cpp Provider 实现思路

## 1. 需求分析

### 1.1 背景
- 当前项目使用 `LlamaCppHttpClient` 作为主要 LLM 客户端
- 已有 `openai_compat` 通用提供者，但缺少专门的 `llama_cpp` 提供者
- 用户需要一个明确的 llama.cpp 入口，并设为默认

### 1.2 目标
- 创建专门的 `llama_cpp` 提供者
- 支持 llama.cpp 特有参数（如 `n_predict`, `n_ctx`, `repeat_penalty` 等）
- 设为默认厂商（优先级最高）
- 复用 OpenAI 兼容逻辑

## 2. 技术设计

### 2.1 类结构

```
LlamaCppProvider
├── 继承: OpenAICompatProvider
├── 特有属性:
│   ├── n_ctx: 上下文长度
│   ├── n_predict: 最大生成 token
│   ├── repeat_penalty: 重复惩罚
│   └── n_gpu_layers: GPU 层数
└── 特有方法:
    ├── get_server_info(): 获取服务器信息
    ├── get_slots_status(): 获取槽位状态
    └── set_n_ctx(): 动态设置上下文
```

### 2.2 API 模式支持

| 模式 | 端点 | 用途 |
|------|------|------|
| openai_compat | `/v1/chat/completions` | 推荐，兼容性好 |
| completion | `/completion` | 原生模式，更多参数 |

### 2.3 特有功能

1. **服务器健康检查**: `GET /health`
2. **槽位状态**: `GET /slots`
3. **模型热加载**: `POST /model`
4. **Embedding**: `POST /embedding`

## 3. 实现步骤

### 步骤 1: 创建 Provider 文件
- 文件: `src/clude_code/llm/providers/llama_cpp.py`
- 继承 `OpenAICompatProvider`
- 添加 llama.cpp 特有参数

### 步骤 2: 注册为默认厂商
- 修改 `providers/__init__.py`，将 `llama_cpp` 放在列表首位
- 更新默认配置

### 步骤 3: 添加特有功能
- 健康检查
- 槽位状态
- 原生 completion API 支持

## 4. 配置示例

```yaml
providers:
  llama_cpp:
    base_url: "http://127.0.0.1:8899"
    default_model: "auto"  # 自动检测
    timeout_s: 120
    extra:
      n_ctx: 32768
      n_predict: 4096
      repeat_penalty: 1.1
```

## 5. 预期效果

- `/providers` 显示 `llama_cpp` 为第 1 位
- 默认启动时自动选择 `llama_cpp`
- 支持 llama.cpp 特有参数
- 向后兼容现有 `openai_compat` 逻辑

## 6. 代码健壮性检查点

- [x] 连接超时处理 (`httpx.TimeoutException`)
- [x] 服务不可用回退 (`httpx.ConnectError`)
- [x] 模型不存在错误处理 (自动检测 `_auto_detect_model`)
- [x] 参数验证 (`validate_config`)
- [x] 多模态内容转换 (`convert_to_openai_vision_format`)
- [x] HTTP 客户端懒加载 (`_get_client`)
- [x] 模型缓存 (`_models_cache`)
- [x] 服务器状态检查 (`get_server_health`)

## 7. 实现完成

✅ **已完成** (2026-01-24)

### 新增文件
- `src/clude_code/llm/providers/llama_cpp.py`

### 修改文件
- `src/clude_code/llm/providers/__init__.py` - 添加 llama_cpp 为首位

### 验证结果
```
Total: 47
Top 5:
  1. llama_cpp       | llama.cpp (本地)            | local   ← 默认
  2. openai_compat   | OpenAI Compatible         | local
  3. openai          | OpenAI                    | cloud
  4. anthropic       | Anthropic                 | cloud
  5. google_gemini   | Google Gemini             | cloud
```

### 特性
| 功能 | 状态 |
|------|------|
| OpenAI 兼容 API | ✅ |
| 原生 /completion API | ✅ |
| 健康检查 | ✅ |
| 槽位状态 | ✅ |
| 服务器属性 | ✅ |
| 多模态支持 | ✅ |
| 自动模型检测 | ✅ |
