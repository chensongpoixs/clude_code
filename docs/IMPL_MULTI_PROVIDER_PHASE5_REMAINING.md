# Phase 5: 剩余厂商接入计划

## 目标

完成 dify_models.md 中全部 51 家厂商的接入。

## 现状分析

### 已实现厂商 (21 家)

| 序号 | 厂商 | 文件 | 状态 |
|------|------|------|------|
| 1 | OpenAI | `openai.py` | ✅ |
| 2 | Azure OpenAI | `azure_openai.py` | ✅ |
| 3 | Anthropic | `anthropic.py` | ✅ |
| 4 | Google Gemini | `google_gemini.py` | ✅ |
| 8 | Mistral AI | `mistral.py` | ✅ |
| 9 | Cohere | `cohere.py` | ✅ |
| 13 | OpenRouter | `openrouter.py` | ✅ |
| 14 | Together.ai | `together.py` | ✅ |
| 17 | Groq | `groq.py` | ✅ |
| 18 | Ollama | `ollama.py` | ✅ |
| 24 | OpenAI Compatible | `openai_compat.py` | ✅ |
| 25 | 通义千问 | `qianwen.py` | ✅ |
| 26 | 文心一言 | `wenxin.py` | ✅ |
| 27 | 月之暗面 | `moonshot.py` | ✅ |
| 28 | 智谱 AI | `zhipu.py` | ✅ |
| 29 | 百川智能 | `baichuan.py` | ✅ |
| 30 | MiniMax | `minimax.py` | ✅ |
| 31 | 讯飞星火 | `spark.py` | ✅ |
| 32 | 腾讯混元 | `hunyuan.py` | ✅ |
| 34 | DeepSeek | `deepseek.py` | ✅ |
| 35 | 硅基流动 | `siliconflow.py` | ✅ |

### 待实现厂商 (30 家)

分为 5 个批次实现：

#### 批次 1: 云厂商 (4 家)
| 序号 | 厂商 | 文件 | API 类型 |
|------|------|------|----------|
| 5 | Google Cloud Vertex AI | `google_vertex.py` | REST |
| 6 | AWS Bedrock | `aws_bedrock.py` | AWS SDK |
| 7 | Amazon SageMaker | `aws_sagemaker.py` | AWS SDK |
| 33 | 腾讯云 | `tencent_cloud.py` | REST |

#### 批次 2: NVIDIA 系列 (4 家)
| 序号 | 厂商 | 文件 | API 类型 |
|------|------|------|----------|
| 10 | NVIDIA API Catalog | `nvidia_catalog.py` | REST |
| 11 | NVIDIA NIM | `nvidia_nim.py` | OpenAI Compatible |
| 12 | NVIDIA Triton | `nvidia_triton.py` | HTTP/gRPC |
| 47 | Nvidia GPU Cloud | (合并到 `nvidia_catalog.py`) | REST |

#### 批次 3: 推理平台 (8 家)
| 序号 | 厂商 | 文件 | API 类型 |
|------|------|------|----------|
| 15 | Replicate | `replicate.py` | REST |
| 16 | Hugging Face | `huggingface.py` | REST |
| 22 | GPUStack | `gpustack.py` | OpenAI Compatible |
| 42 | PerfXCloud | `perfxcloud.py` | OpenAI Compatible |
| 43 | Lepton AI | `lepton.py` | OpenAI Compatible |
| 44 | novita.ai | `novita.py` | REST |
| 45 | Jina AI | `jina.py` | REST |
| 46 | Xorbits Inference | `xorbits.py` | OpenAI Compatible |

#### 批次 4: 本地/私有化部署 (5 家)
| 序号 | 厂商 | 文件 | API 类型 |
|------|------|------|----------|
| 19 | LocalAI | `localai.py` | OpenAI Compatible |
| 20 | Xinference | `xinference.py` | OpenAI Compatible |
| 21 | OpenLLM | `openllm.py` | OpenAI Compatible |
| 23 | Text Embedding Inference | `text_embedding.py` | REST |
| 48-50 | 通用兼容 | (已有 `openai_compat.py`) | OpenAI Compatible |

#### 批次 5: 国内补充 (9 家)
| 序号 | 厂商 | 文件 | API 类型 |
|------|------|------|----------|
| 36 | 魔搭社区 | `modelscope.py` | REST |
| 37 | Zhipu MaaS | (合并到 `zhipu.py`) | REST |
| 38 | Baidu Qianfan | `baidu_qianfan.py` | REST |
| 39 | Alibaba Cloud PAI | `alibaba_pai.py` | REST |
| 40 | Tencent TI | `tencent_ti.py` | REST |
| 41 | Stepfun | `stepfun.py` | REST |
| 51 | 七牛云 | `qiniu.py` | REST |

---

## 实现策略

### 1. OpenAI Compatible 复用

大部分平台支持 OpenAI 兼容 API，只需继承 `openai_compat.py` 并配置：
- `base_url`
- `api_key_env`
- `default_model`
- 模型列表

### 2. SDK 依赖

部分厂商需要额外 SDK：
- AWS: `boto3`
- Google Cloud: `google-cloud-aiplatform`
- Hugging Face: `huggingface_hub`

### 3. 统一接口

所有厂商实现相同的 `LLMProvider` 接口：
```python
class XXXProvider(LLMProvider):
    def chat(self, messages, **kwargs) -> str: ...
    def list_models(self) -> list[ModelInfo]: ...
    def get_model_info(self, model_id) -> ModelInfo | None: ...
```

---

## 实施步骤

1. ✅ 写计划文档（本文件）
2. ✅ 批次 1: 云厂商 (4 家)
3. ✅ 批次 2: NVIDIA 系列 (3 家)
4. ✅ 批次 3: 推理平台 (8 家)
5. ✅ 批次 4: 本地部署 (4 家)
6. ✅ 批次 5: 国内补充 (6 家)
7. ✅ 编译检查 & 汇报

---

## 完成汇报

### 新增厂商 (25 家)

| 批次 | 厂商数量 | 厂商列表 |
|------|----------|----------|
| 批次 1: 云厂商 | 4 | Google Vertex AI, AWS Bedrock, AWS SageMaker, 腾讯云 |
| 批次 2: NVIDIA | 3 | NVIDIA NIM, NVIDIA Triton, NVIDIA Catalog |
| 批次 3: 推理平台 | 8 | Replicate, Hugging Face, Lepton, novita.ai, Jina, GPUStack, PerfXCloud, Xorbits |
| 批次 4: 本地部署 | 4 | LocalAI, Xinference, OpenLLM, Text Embedding |
| 批次 5: 国内补充 | 6 | 阶跃星辰, 魔搭社区, 百度千帆, 阿里云 PAI, 腾讯云 TI, 七牛云 |

### 总计

- **原有厂商**: 21 家
- **新增厂商**: 25 家
- **总计**: 46 家

### 验证结果

```bash
# 编译检查
python -m compileall -q src/clude_code/llm/providers/  # ✅ 通过

# 厂商注册
已注册厂商数量: 46（含运行时依赖如 requests/boto3）
```

---

## 文件结构

```
src/clude_code/llm/providers/
├── __init__.py
├── openai_compat.py      # 基础兼容层
├── openai.py             # ✅ 已实现
├── anthropic.py          # ✅ 已实现
├── google_gemini.py      # ✅ 已实现
├── google_vertex.py      # ⏳ 待实现
├── aws_bedrock.py        # ⏳ 待实现
├── aws_sagemaker.py      # ⏳ 待实现
├── nvidia_catalog.py     # ⏳ 待实现
├── nvidia_nim.py         # ⏳ 待实现
├── nvidia_triton.py      # ⏳ 待实现
├── replicate.py          # ⏳ 待实现
├── huggingface.py        # ⏳ 待实现
├── localai.py            # ⏳ 待实现
├── xinference.py         # ⏳ 待实现
├── openllm.py            # ⏳ 待实现
├── gpustack.py           # ⏳ 待实现
├── perfxcloud.py         # ⏳ 待实现
├── lepton.py             # ⏳ 待实现
├── novita.py             # ⏳ 待实现
├── jina.py               # ⏳ 待实现
├── xorbits.py            # ⏳ 待实现
├── text_embedding.py     # ⏳ 待实现
├── modelscope.py         # ⏳ 待实现
├── baidu_qianfan.py      # ⏳ 待实现
├── alibaba_pai.py        # ⏳ 待实现
├── tencent_cloud.py      # ⏳ 待实现
├── tencent_ti.py         # ⏳ 待实现
├── stepfun.py            # ⏳ 待实现
├── qiniu.py              # ⏳ 待实现
└── ... (已实现的 21 个)
```

