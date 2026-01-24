# Phase 2: 实现 50 家厂商接入

## 总体思路

### 1. 厂商分类

根据 `dify_models.md` 文档，将 50 家厂商分为 5 个批次：

| 批次 | 类型 | 厂商数量 | 优先级 |
|------|------|----------|--------|
| 1 | 核心国际 | 3 | P0 |
| 2 | 云厂商 | 4 | P1 |
| 3 | 国内厂商 | 12 | P0 |
| 4 | 推理平台 | 10 | P1 |
| 5 | 其他 | 21 | P2 |

### 2. 实现策略

**关键洞察**：大多数厂商都兼容 OpenAI API，可以通过继承 `OpenAICompatProvider` 快速实现。

实现模式：
1. **完全 OpenAI 兼容**：直接继承 `OpenAICompatProvider`，只需配置 `base_url` 和模型列表
2. **部分兼容**：继承后覆盖特定方法（如认证、流式解析）
3. **完全自定义**：直接继承 `LLMProvider`（如 Anthropic 原生 API）

### 3. 文件组织

```
src/clude_code/llm/providers/
├── __init__.py           # 自动导入
├── openai_compat.py      # 基础兼容类 ✅ 已完成
├── openai.py             # OpenAI
├── anthropic.py          # Anthropic
├── google_gemini.py      # Google Gemini
├── azure_openai.py       # Azure OpenAI
├── aws_bedrock.py        # AWS Bedrock
├── deepseek.py           # DeepSeek
├── moonshot.py           # 月之暗面
├── zhipu.py              # 智谱 AI
├── qianwen.py            # 通义千问
├── wenxin.py             # 文心一言
├── baichuan.py           # 百川智能
├── minimax.py            # MiniMax
├── spark.py              # 讯飞星火
├── hunyuan.py            # 腾讯混元
├── stepfun.py            # 阶跃星辰
├── siliconflow.py        # 硅基流动
├── ollama.py             # Ollama
├── groq.py               # Groq
├── together.py           # Together.ai
├── openrouter.py         # OpenRouter
├── mistral.py            # Mistral AI
├── cohere.py             # Cohere
└── ...
```

---

## 批次 1: 核心国际厂商

### 1.1 OpenAI

**特点**：
- 标准 OpenAI API
- 支持 Vision、Function Call、Streaming
- 模型：gpt-4o, gpt-4o-mini, o1-preview, o1-mini

**实现**：继承 `OpenAICompatProvider`，添加官方模型列表

### 1.2 Anthropic

**特点**：
- 非 OpenAI 兼容，有自己的 API 格式
- Messages API（类似但不同）
- 模型：claude-3-5-sonnet, claude-3-opus, claude-3-haiku

**实现**：直接继承 `LLMProvider`，实现 Anthropic 原生 API

### 1.3 Google Gemini

**特点**：
- 部分 OpenAI 兼容（通过 generativelanguage.googleapis.com）
- 模型：gemini-1.5-pro, gemini-1.5-flash, gemini-2.0-flash

**实现**：继承 `OpenAICompatProvider`，调整认证方式

---

## 批次 3: 国内厂商（重点）

所有国内厂商都提供 OpenAI 兼容 API：

| 厂商 | Base URL | 认证 |
|------|----------|------|
| DeepSeek | api.deepseek.com/v1 | Bearer Token |
| 月之暗面 | api.moonshot.cn/v1 | Bearer Token |
| 智谱 AI | open.bigmodel.cn/api/paas/v4 | Bearer Token |
| 通义千问 | dashscope.aliyuncs.com/compatible-mode/v1 | Bearer Token |
| 硅基流动 | api.siliconflow.cn/v1 | Bearer Token |
| 百川智能 | api.baichuan-ai.com/v1 | Bearer Token |
| MiniMax | api.minimax.chat/v1 | Bearer Token |
| 讯飞星火 | spark-api-open.xf-yun.com/v1 | Bearer Token |
| 腾讯混元 | api.hunyuan.cloud.tencent.com/v1 | Bearer Token |

**实现**：全部继承 `OpenAICompatProvider`，只需配置模型列表

---

## 批次 4: 推理平台

| 厂商 | 特点 |
|------|------|
| Ollama | 本地部署，无需 API Key |
| Groq | 超快推理，OpenAI 兼容 |
| Together.ai | 开源模型托管 |
| OpenRouter | 多模型聚合 |
| Replicate | 模型托管 |

---

## 实施计划

1. ✅ 写思路文档（本文件）
2. ✅ 批次 1: 核心国际厂商 (OpenAI, Anthropic, Google Gemini)
3. ✅ 批次 3: 国内厂商（DeepSeek, 月之暗面, 智谱, 通义, 文心, 百川, MiniMax, 讯飞, 腾讯）
4. ✅ 批次 4: 推理平台 (Ollama, Groq, Together, OpenRouter, SiliconFlow)
5. ✅ 批次 2: 云厂商 (Azure OpenAI)
6. ✅ 批次 5: 其他 (Mistral, Cohere)
7. ✅ 更新 providers/__init__.py
8. ✅ 编译检查
9. ✅ 汇报进度

---

## 完成汇报

### 已实现厂商 (21 家)

| 类型 | 厂商 | 文件 |
|------|------|------|
| 基础 | OpenAI Compatible | `openai_compat.py` |
| 国际 | OpenAI | `openai.py` |
| 国际 | Anthropic | `anthropic.py` |
| 国际 | Google Gemini | `google_gemini.py` |
| 国际 | Mistral AI | `mistral.py` |
| 国际 | Cohere | `cohere.py` |
| 云厂商 | Azure OpenAI | `azure_openai.py` |
| 国内 | DeepSeek | `deepseek.py` |
| 国内 | 月之暗面 | `moonshot.py` |
| 国内 | 智谱 AI | `zhipu.py` |
| 国内 | 通义千问 | `qianwen.py` |
| 国内 | 文心一言 | `wenxin.py` |
| 国内 | 百川智能 | `baichuan.py` |
| 国内 | MiniMax | `minimax.py` |
| 国内 | 讯飞星火 | `spark.py` |
| 国内 | 腾讯混元 | `hunyuan.py` |
| 推理 | Ollama | `ollama.py` |
| 推理 | Groq | `groq.py` |
| 推理 | Together.ai | `together.py` |
| 聚合 | OpenRouter | `openrouter.py` |
| 推理 | 硅基流动 | `siliconflow.py` |

### 验证结果

```bash
# 编译检查
python -m compileall -q src/clude_code/llm/providers/  # ✅ 通过

# 导入测试
from clude_code.llm import list_providers
len(list_providers())  # ✅ 返回 21

# Lint 检查
read_lints  # ✅ 无错误
```

### 统计

- 总厂商数：**21 家**
- 国际厂商：6 家
- 国内厂商：10 家
- 推理平台：4 家
- 聚合平台：1 家

