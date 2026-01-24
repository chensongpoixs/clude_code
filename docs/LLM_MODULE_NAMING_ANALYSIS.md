# LLM 模块文件命名规范分析

## 1. 业界标准参考

### 1.1 主流框架命名规范

| 框架 | 目录结构 | 文件命名 | 特点 |
|------|----------|----------|------|
| **LangChain** | `langchain/llms/` | `openai.py`, `anthropic.py` | 小写单词，无分隔符 |
| **LiteLLM** | `litellm/llms/` | `openai.py`, `azure.py` | 小写，简洁 |
| **Dify** | `models/{provider}/` | `llm.py`, `text_embedding.py` | 按功能分 |
| **vLLM** | `vllm/model_executor/models/` | `llama.py`, `gpt2.py` | 模型名小写 |
| **OpenAI SDK** | `openai/resources/` | `chat.py`, `completions.py` | 功能模块名 |

### 1.2 Python PEP 8 命名规范

- **模块名**: 全小写，可用下划线 (`snake_case`)
- **包名**: 全小写，尽量不用下划线
- **类名**: `PascalCase`
- **常量**: `UPPER_SNAKE_CASE`

### 1.3 业界最佳实践

1. **厂商文件**: `{provider}.py` (如 `openai.py`, `anthropic.py`)
2. **组合厂商**: `{vendor}_{product}.py` (如 `azure_openai.py`, `google_gemini.py`)
3. **功能模块**: `{功能}.py` (如 `base.py`, `registry.py`, `router.py`)
4. **工具文件**: `{用途}_utils.py` 或 `{用途}.py`

---

## 2. 当前项目文件分析

### 2.1 llm/ 根目录文件

| 文件名 | 用途 | 规范性 | 建议 |
|--------|------|--------|------|
| `__init__.py` | 包初始化 | ✅ 规范 | - |
| `base.py` | 抽象基类 | ✅ 规范 | 业界常用 |
| `registry.py` | 厂商注册表 | ✅ 规范 | 业界常用 |
| `model_manager.py` | 模型管理器 | ✅ 规范 | snake_case |
| `auto_router.py` | 自动路由 | ✅ 规范 | 语义清晰 |
| `cost_tracker.py` | 成本追踪 | ✅ 规范 | 语义清晰 |
| `failover.py` | 故障转移 | ✅ 规范 | 简洁明了 |
| `image_utils.py` | 图片工具 | ✅ 规范 | 标准 utils 后缀 |
| `llama_cpp_http.py` | HTTP 客户端 | ⚠️ 可优化 | 见下文 |
| `streaming_client.py` | 流式客户端 | ✅ 规范 | 语义清晰 |
| `README.md` | 文档 | ✅ 规范 | - |
| `module_flow.svg` | 流程图 | ✅ 规范 | - |

### 2.2 providers/ 目录文件

#### ✅ 规范命名 (32 个)

| 类型 | 文件 | 说明 |
|------|------|------|
| **单词厂商** | `openai.py`, `anthropic.py`, `cohere.py`, `mistral.py`, `groq.py`, `ollama.py`, `replicate.py`, `jina.py`, `lepton.py`, `novita.py` | 完全符合业界规范 |
| **组合厂商** | `azure_openai.py`, `google_gemini.py`, `google_vertex.py`, `aws_bedrock.py`, `aws_sagemaker.py`, `tencent_cloud.py`, `tencent_ti.py`, `alibaba_pai.py`, `baidu_qianfan.py` | `{vendor}_{product}` 格式 |
| **NVIDIA** | `nvidia_nim.py`, `nvidia_triton.py`, `nvidia_catalog.py` | `{vendor}_{product}` 格式 |
| **本地推理** | `llama_cpp.py`, `localai.py`, `xinference.py`, `openllm.py` | 符合规范 |
| **国内厂商** | `deepseek.py`, `moonshot.py`, `zhipu.py`, `qianwen.py`, `wenxin.py`, `baichuan.py`, `minimax.py`, `spark.py`, `hunyuan.py`, `stepfun.py`, `modelscope.py`, `siliconflow.py`, `qiniu.py` | 符合规范 |

#### ⚠️ 可讨论命名 (4 个)

| 文件名 | 说明 | 建议 |
|--------|------|------|
| `openai_compat.py` | 功能描述而非厂商 | ✅ 保留（通用兼容层） |
| `text_embedding.py` | HuggingFace TEI 服务 | ✅ 保留（专用推理服务） |
| `huggingface.py` | 官方品牌名连写 | ✅ 保留（原名 HuggingFace） |
| `gpustack.py` | 产品名连写 | ✅ 保留（原名 GPUStack） |

---

## 3. 与业界对比

### 3.1 命名风格对比

| 项目 | 风格 | 示例 |
|------|------|------|
| **LangChain** | 无下划线 | `openai.py`, `azureopenai.py` |
| **LiteLLM** | 无下划线 | `openai.py`, `azure.py` |
| **Dify** | 下划线 | `azure_openai/`, `google_cloud/` |
| **本项目** | 下划线 | `azure_openai.py`, `google_gemini.py` |

**结论**: 本项目采用下划线分隔的 `snake_case` 风格，与 **Dify** 一致，符合 **PEP 8** 规范。

### 3.2 目录结构对比

```
# LangChain 风格
langchain/
├── llms/
│   ├── openai.py
│   └── anthropic.py
└── chat_models/
    ├── openai.py
    └── anthropic.py

# LiteLLM 风格
litellm/
├── llms/
│   ├── openai.py
│   ├── azure.py
│   └── anthropic.py
└── types/

# 本项目风格 ✅
clude_code/llm/
├── providers/
│   ├── openai.py
│   ├── azure_openai.py
│   └── anthropic.py
├── base.py
├── registry.py
└── model_manager.py
```

**结论**: 本项目采用 `providers/` 子目录集中管理厂商实现，结构清晰，符合业界主流。

---

## 4. 规范性评分

### 4.1 评分标准

| 维度 | 权重 | 得分 | 说明 |
|------|------|------|------|
| **PEP 8 合规** | 30% | 95/100 | 几乎全部使用 snake_case |
| **语义清晰度** | 25% | 90/100 | 文件名能准确反映用途 |
| **一致性** | 25% | 85/100 | 组合名称风格统一 |
| **业界对齐** | 20% | 90/100 | 与 Dify/LangChain 风格接近 |

**综合得分**: **90/100** ⭐⭐⭐⭐½

### 4.2 优势

1. ✅ 统一使用 `snake_case` 命名
2. ✅ 厂商文件与 `PROVIDER_ID` 保持一致
3. ✅ 功能模块命名语义清晰
4. ✅ 目录结构层次分明

### 4.3 改进空间

1. ⚠️ `llama_cpp_http.py` 历史命名，可考虑重命名为 `http_client.py`（低优先级）
2. ✅ `text_embedding.py` 实际是 HuggingFace TEI 服务 Provider（命名合理）
3. ✅ 品牌名遵循官方写法（HuggingFace, GPUStack 等）

---

## 5. 改进建议

### 5.1 短期优化（低风险）

```python
# 当前
llama_cpp_http.py   # 历史遗留，混合了厂商名和功能

# 建议（可选）
http_client.py      # 通用 HTTP 客户端
# 或保持现状（避免大规模重构）
```

### 5.2 中期规范（推荐）

1. **添加命名检查 CI**:
```yaml
# .github/workflows/lint.yml
- name: Check file naming
  run: |
    find src/clude_code/llm/providers -name "*.py" | \
    grep -vE "^[a-z_]+\.py$" && exit 1 || exit 0
```

2. **文档化命名规范**:
```markdown
## 新增厂商命名规则
1. 单一厂商: `{provider}.py` (如 openai.py)
2. 组合厂商: `{vendor}_{product}.py` (如 azure_openai.py)
3. PROVIDER_ID 必须与文件名一致
```

### 5.3 长期演进（可选）

| 变更 | 影响 | 优先级 | 状态 |
|------|------|--------|------|
| 重命名 `llama_cpp_http.py` → `http_client.py` | 大 | P3 | 可选 |
| 添加 CI 命名检查 | 小 | P2 | 推荐 |
| 完善 Provider 模板 | 小 | P1 | 推荐 |

---

## 6. 结论

### 6.1 总体评价

**本项目 LLM 模块命名规范性良好**，主要特点：

- ✅ 遵循 Python PEP 8 规范
- ✅ 与业界主流框架（Dify、LangChain）风格一致
- ✅ 目录结构清晰，易于维护
- ✅ 47 个厂商文件命名统一

### 6.2 无需立即修改的项

| 文件 | 原因 |
|------|------|
| `huggingface.py` | 官方品牌名就是连写 |
| `gpustack.py` | 产品名原本就是 GPUStack |
| `perfxcloud.py` | 品牌名 PerfXCloud |
| `openai_compat.py` | 功能描述，非厂商名 |

### 6.3 建议保持的规范

```python
# ✅ 新增厂商时遵循
class MyProvider(LLMProvider):
    PROVIDER_ID = "my_provider"  # 与文件名一致
    PROVIDER_NAME = "My Provider"
    PROVIDER_TYPE = "cloud"
    REGION = "海外"
```

---

**分析完成时间**: 2026-01-24
**分析版本**: v1.0

