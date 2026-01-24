# 多模型厂商接入设计方案

## 1. 背景与目标

### 1.1 当前状态
- 仅支持单一 `llama_cpp_http` 提供商
- 配置写死在 `LLMConfig` 中
- 无法动态切换不同厂商

### 1.2 目标
参考 Dify 平台，支持 50+ 模型提供商：
- 国际主流：OpenAI、Anthropic、Google Gemini、Azure、AWS Bedrock
- 国内厂商：通义千问、文心一言、智谱、DeepSeek、月之暗面
- 推理平台：Ollama、Xinference、SiliconFlow、OpenRouter
- 自定义：任意 OpenAI 兼容 API

### 1.3 核心需求
1. **每个厂商一个独立文件** - 便于维护和扩展
2. **全局配置管理** - 统一的厂商配置
3. **运行时切换** - 支持查看、选择、切换厂商/模型
4. **统一接口** - 所有厂商暴露相同的调用接口

---

## 2. 架构设计

### 2.1 目录结构

```
src/clude_code/llm/
├── __init__.py                 # 导出统一接口
├── base.py                     # 抽象基类 LLMProvider
├── model_manager.py            # 全局模型管理器（已有，需扩展）
├── registry.py                 # 厂商注册表
│
├── providers/                  # 各厂商实现（每个厂商一个文件）
│   ├── __init__.py
│   ├── openai.py              # OpenAI / GPT
│   ├── anthropic.py           # Anthropic / Claude
│   ├── azure_openai.py        # Azure OpenAI
│   ├── google_gemini.py       # Google Gemini
│   ├── aws_bedrock.py         # AWS Bedrock
│   ├── ollama.py              # Ollama (本地)
│   ├── llama_cpp.py           # llama.cpp (本地)
│   ├── siliconflow.py         # 硅基流动
│   ├── deepseek.py            # DeepSeek
│   ├── zhipu.py               # 智谱 AI
│   ├── moonshot.py            # 月之暗面
│   ├── qianwen.py             # 通义千问
│   ├── wenxin.py              # 文心一言
│   └── openai_compat.py       # 通用 OpenAI 兼容（兜底）
│
└── image_utils.py              # 图片处理（已有）
```

### 2.2 核心类设计

#### 2.2.1 抽象基类 `LLMProvider`

```python
# src/clude_code/llm/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

@dataclass
class ModelInfo:
    """模型信息"""
    id: str
    name: str
    provider: str
    context_window: int = 4096
    max_output_tokens: int = 4096
    supports_vision: bool = False
    supports_function_call: bool = False
    supports_streaming: bool = True
    pricing: dict | None = None  # {"input": 0.001, "output": 0.002} per 1K tokens

@dataclass
class ProviderConfig:
    """厂商配置"""
    name: str
    api_key: str = ""
    base_url: str = ""
    api_version: str = ""
    organization: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

class LLMProvider(ABC):
    """LLM 厂商抽象基类"""
    
    # 厂商元信息
    PROVIDER_NAME: str = ""
    PROVIDER_TYPE: str = ""  # cloud | local | aggregator
    REGION: str = ""         # 海外 | 国内 | 通用
    
    def __init__(self, config: ProviderConfig):
        self.config = config
    
    @abstractmethod
    def chat(self, messages: list[ChatMessage], **kwargs) -> str:
        """同步聊天"""
        pass
    
    @abstractmethod
    async def chat_async(self, messages: list[ChatMessage], **kwargs) -> str:
        """异步聊天"""
        pass
    
    @abstractmethod
    def chat_stream(self, messages: list[ChatMessage], **kwargs):
        """流式聊天"""
        pass
    
    @abstractmethod
    def list_models(self) -> list[ModelInfo]:
        """获取可用模型列表"""
        pass
    
    @abstractmethod
    def get_model_info(self, model_id: str) -> ModelInfo | None:
        """获取单个模型信息"""
        pass
    
    def validate_config(self) -> tuple[bool, str]:
        """验证配置有效性"""
        return True, "OK"
    
    def test_connection(self) -> tuple[bool, str]:
        """测试连接"""
        pass
```

#### 2.2.2 厂商注册表 `ProviderRegistry`

```python
# src/clude_code/llm/registry.py
from typing import Type

class ProviderRegistry:
    """厂商注册表（单例）"""
    
    _instance = None
    _providers: dict[str, Type[LLMProvider]] = {}
    _instances: dict[str, LLMProvider] = {}
    
    @classmethod
    def register(cls, name: str):
        """装饰器：注册厂商"""
        def decorator(provider_class: Type[LLMProvider]):
            cls._providers[name] = provider_class
            return provider_class
        return decorator
    
    @classmethod
    def get_provider(cls, name: str, config: ProviderConfig) -> LLMProvider:
        """获取厂商实例"""
        if name not in cls._providers:
            raise ValueError(f"未知厂商: {name}")
        
        key = f"{name}:{config.api_key[:8] if config.api_key else 'default'}"
        if key not in cls._instances:
            cls._instances[key] = cls._providers[name](config)
        return cls._instances[key]
    
    @classmethod
    def list_providers(cls) -> list[dict]:
        """列出所有已注册厂商"""
        return [
            {
                "name": name,
                "type": p.PROVIDER_TYPE,
                "region": p.REGION,
            }
            for name, p in cls._providers.items()
        ]
```

### 2.3 配置设计

#### 2.3.1 全局配置 `~/.clude/.clude.yaml`

```yaml
# 多厂商配置
providers:
  # 默认厂商
  default: openai
  
  # OpenAI
  openai:
    enabled: true
    api_key: ${OPENAI_API_KEY}
    base_url: https://api.openai.com/v1
    default_model: gpt-4o
    
  # Anthropic
  anthropic:
    enabled: true
    api_key: ${ANTHROPIC_API_KEY}
    default_model: claude-3-5-sonnet-latest
    
  # Azure OpenAI
  azure_openai:
    enabled: false
    api_key: ${AZURE_OPENAI_API_KEY}
    base_url: https://your-resource.openai.azure.com
    api_version: 2024-02-15-preview
    deployment_map:
      gpt-4o: your-gpt4o-deployment
      
  # DeepSeek
  deepseek:
    enabled: true
    api_key: ${DEEPSEEK_API_KEY}
    base_url: https://api.deepseek.com/v1
    default_model: deepseek-chat
    
  # 月之暗面
  moonshot:
    enabled: true
    api_key: ${MOONSHOT_API_KEY}
    base_url: https://api.moonshot.cn/v1
    default_model: moonshot-v1-8k
    
  # 硅基流动
  siliconflow:
    enabled: true
    api_key: ${SILICONFLOW_API_KEY}
    base_url: https://api.siliconflow.cn/v1
    default_model: deepseek-ai/DeepSeek-V3
    
  # Ollama (本地)
  ollama:
    enabled: true
    base_url: http://127.0.0.1:11434
    default_model: llama3.2
    
  # llama.cpp (本地)
  llama_cpp:
    enabled: true
    base_url: http://127.0.0.1:8899
    default_model: gemma-3-12b-it
    
  # 通用 OpenAI 兼容
  openai_compat:
    enabled: true
    api_key: ${CUSTOM_API_KEY}
    base_url: ${CUSTOM_BASE_URL}
    default_model: ${CUSTOM_MODEL}
```

#### 2.3.2 配置数据模型

```python
# src/clude_code/config/config.py 扩展

class ProviderConfigItem(BaseModel):
    """单个厂商配置"""
    enabled: bool = True
    api_key: str = ""
    base_url: str = ""
    api_version: str = ""
    default_model: str = ""
    extra: dict[str, Any] = Field(default_factory=dict)

class ProvidersConfig(BaseModel):
    """多厂商配置"""
    default: str = "openai"
    openai: ProviderConfigItem = Field(default_factory=ProviderConfigItem)
    anthropic: ProviderConfigItem = Field(default_factory=ProviderConfigItem)
    azure_openai: ProviderConfigItem = Field(default_factory=ProviderConfigItem)
    deepseek: ProviderConfigItem = Field(default_factory=ProviderConfigItem)
    moonshot: ProviderConfigItem = Field(default_factory=ProviderConfigItem)
    siliconflow: ProviderConfigItem = Field(default_factory=ProviderConfigItem)
    ollama: ProviderConfigItem = Field(default_factory=ProviderConfigItem)
    llama_cpp: ProviderConfigItem = Field(default_factory=ProviderConfigItem)
    openai_compat: ProviderConfigItem = Field(default_factory=ProviderConfigItem)
```

---

## 3. 实现步骤

### Phase 1: 基础架构（P0）
| 步骤 | 内容 | 文件 |
|------|------|------|
| 1.1 | 创建抽象基类 `LLMProvider` | `llm/base.py` |
| 1.2 | 创建厂商注册表 `ProviderRegistry` | `llm/registry.py` |
| 1.3 | 扩展配置数据模型 | `config/config.py` |
| 1.4 | 重构 `ModelManager` 支持多厂商 | `llm/model_manager.py` |

### Phase 2: 核心厂商实现（P1）
| 步骤 | 内容 | 文件 |
|------|------|------|
| 2.1 | OpenAI 提供商 | `llm/providers/openai.py` |
| 2.2 | Anthropic 提供商 | `llm/providers/anthropic.py` |
| 2.3 | 通用 OpenAI 兼容 | `llm/providers/openai_compat.py` |
| 2.4 | Ollama 提供商 | `llm/providers/ollama.py` |
| 2.5 | llama.cpp 提供商（重构现有） | `llm/providers/llama_cpp.py` |

### Phase 3: 国内厂商实现（P2）
| 步骤 | 内容 | 文件 |
|------|------|------|
| 3.1 | DeepSeek | `llm/providers/deepseek.py` |
| 3.2 | 月之暗面 | `llm/providers/moonshot.py` |
| 3.3 | 智谱 AI | `llm/providers/zhipu.py` |
| 3.4 | 硅基流动 | `llm/providers/siliconflow.py` |
| 3.5 | 通义千问 | `llm/providers/qianwen.py` |

### Phase 4: CLI 集成（P3）
| 步骤 | 内容 | 文件 |
|------|------|------|
| 4.1 | `/providers` 命令 - 列出厂商 | `cli/slash_commands.py` |
| 4.2 | `/provider <name>` - 切换厂商 | `cli/slash_commands.py` |
| 4.3 | `/models` 命令 - 列出模型 | `cli/slash_commands.py` |
| 4.4 | `/model <name>` - 切换模型 | `cli/slash_commands.py` |
| 4.5 | `clude providers` CLI 命令 | `cli/providers_cmd.py` |

### Phase 5: 高级功能（P4）
| 步骤 | 内容 | 文件 |
|------|------|------|
| 5.1 | 模型能力检测（Vision/Function Call） | `llm/capabilities.py` |
| 5.2 | 模型自动路由（按任务类型选模型） | `llm/router.py` |
| 5.3 | 成本追踪与预算控制 | `llm/cost_tracker.py` |
| 5.4 | 故障转移（Failover） | `llm/failover.py` |

---

## 4. 各厂商实现示例

### 4.1 OpenAI 提供商

```python
# src/clude_code/llm/providers/openai.py
from ..base import LLMProvider, ProviderConfig, ModelInfo, ChatMessage
from ..registry import ProviderRegistry
import httpx

@ProviderRegistry.register("openai")
class OpenAIProvider(LLMProvider):
    PROVIDER_NAME = "OpenAI"
    PROVIDER_TYPE = "cloud"
    REGION = "海外"
    
    MODELS = [
        ModelInfo(id="gpt-4o", name="GPT-4o", provider="openai", 
                  context_window=128000, max_output_tokens=16384,
                  supports_vision=True, supports_function_call=True),
        ModelInfo(id="gpt-4o-mini", name="GPT-4o Mini", provider="openai",
                  context_window=128000, max_output_tokens=16384,
                  supports_vision=True, supports_function_call=True),
        ModelInfo(id="gpt-4-turbo", name="GPT-4 Turbo", provider="openai",
                  context_window=128000, max_output_tokens=4096,
                  supports_vision=True, supports_function_call=True),
        ModelInfo(id="o1-preview", name="o1 Preview", provider="openai",
                  context_window=128000, max_output_tokens=32768),
        ModelInfo(id="o1-mini", name="o1 Mini", provider="openai",
                  context_window=128000, max_output_tokens=65536),
    ]
    
    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self.base_url = config.base_url or "https://api.openai.com/v1"
        self.client = httpx.Client(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json",
            },
            timeout=120.0,
        )
    
    def chat(self, messages: list[ChatMessage], **kwargs) -> str:
        model = kwargs.get("model", self.config.extra.get("default_model", "gpt-4o"))
        payload = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": kwargs.get("temperature", 0.2),
            "max_tokens": kwargs.get("max_tokens", 4096),
        }
        resp = self.client.post("/chat/completions", json=payload)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    
    def list_models(self) -> list[ModelInfo]:
        return self.MODELS
    
    def get_model_info(self, model_id: str) -> ModelInfo | None:
        for m in self.MODELS:
            if m.id == model_id:
                return m
        return None
```

### 4.2 DeepSeek 提供商

```python
# src/clude_code/llm/providers/deepseek.py
from ..base import LLMProvider, ProviderConfig, ModelInfo
from ..registry import ProviderRegistry

@ProviderRegistry.register("deepseek")
class DeepSeekProvider(LLMProvider):
    PROVIDER_NAME = "DeepSeek"
    PROVIDER_TYPE = "cloud"
    REGION = "国内"
    
    MODELS = [
        ModelInfo(id="deepseek-chat", name="DeepSeek Chat", provider="deepseek",
                  context_window=64000, max_output_tokens=8192,
                  supports_function_call=True),
        ModelInfo(id="deepseek-coder", name="DeepSeek Coder", provider="deepseek",
                  context_window=64000, max_output_tokens=8192,
                  supports_function_call=True),
        ModelInfo(id="deepseek-reasoner", name="DeepSeek R1", provider="deepseek",
                  context_window=64000, max_output_tokens=8192),
    ]
    
    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self.base_url = config.base_url or "https://api.deepseek.com/v1"
        # 复用 OpenAI 兼容逻辑...
```

---

## 5. CLI 交互设计

### 5.1 查看厂商列表

```bash
$ clude providers list

╭──────────────────────────────────────────────────────────────╮
│                    可用模型厂商 (8/50)                        │
├──────────────────────────────────────────────────────────────┤
│  序号  │  厂商名称       │  类型    │  区域  │  状态    │  默认模型              │
├────────┼─────────────────┼──────────┼────────┼──────────┼────────────────────────┤
│  1     │  ★ openai       │  cloud   │  海外  │  ✓ 已配置 │  gpt-4o               │
│  2     │  anthropic      │  cloud   │  海外  │  ✓ 已配置 │  claude-3-5-sonnet    │
│  3     │  deepseek       │  cloud   │  国内  │  ✓ 已配置 │  deepseek-chat        │
│  4     │  moonshot       │  cloud   │  国内  │  ✗ 未配置 │  -                    │
│  5     │  ★ llama_cpp    │  local   │  通用  │  ✓ 运行中 │  gemma-3-12b-it       │
│  6     │  ollama         │  local   │  通用  │  ✗ 未运行 │  -                    │
╰──────────────────────────────────────────────────────────────╯

★ = 当前使用

使用 `/provider <name>` 切换厂商
使用 `clude providers config <name>` 配置厂商
```

### 5.2 查看模型列表

```bash
$ clude models list --provider openai

╭──────────────────────────────────────────────────────────────╮
│                 OpenAI 可用模型 (5)                           │
├──────────────────────────────────────────────────────────────┤
│  模型 ID          │  名称           │  上下文    │  能力             │
├───────────────────┼─────────────────┼────────────┼───────────────────┤
│  ★ gpt-4o         │  GPT-4o         │  128K      │  🖼️ 📞 🌊          │
│  gpt-4o-mini      │  GPT-4o Mini    │  128K      │  🖼️ 📞 🌊          │
│  gpt-4-turbo      │  GPT-4 Turbo    │  128K      │  🖼️ 📞 🌊          │
│  o1-preview       │  o1 Preview     │  128K      │  🌊               │
│  o1-mini          │  o1 Mini        │  128K      │  🌊               │
╰──────────────────────────────────────────────────────────────╯

🖼️ = Vision  📞 = Function Call  🌊 = Streaming
★ = 当前使用

使用 `/model <id>` 切换模型
```

### 5.3 在 Chat 中切换

```
you (): /providers
[显示厂商列表]

you (): /provider deepseek
✓ 已切换到厂商: DeepSeek (deepseek-chat)

you (): /models
[显示 DeepSeek 模型列表]

you (): /model deepseek-coder
✓ 已切换到模型: deepseek-coder
```

---

## 6. 验收标准

### 6.1 功能验收
- [ ] 支持至少 10 个厂商
- [ ] 每个厂商独立文件
- [ ] 统一的 `LLMProvider` 接口
- [ ] CLI 命令完整
- [ ] 配置热加载

### 6.2 非功能验收
- [ ] 厂商切换 < 100ms
- [ ] 模型列表缓存
- [ ] 错误处理完善
- [ ] 文档完整

---

## 7. 风险与缓解

| 风险 | 缓解措施 |
|------|----------|
| API 格式差异 | 统一抽象层 + 适配器模式 |
| 认证方式不同 | 支持多种认证策略 |
| 流式响应差异 | 统一 SSE 解析 |
| 国内网络问题 | 支持代理配置 |

---

## 8. 状态

- [x] Phase 1: 基础架构（LLMProvider, ProviderRegistry, ProvidersConfig, ModelManager）
- [x] Phase 2: 核心厂商（21 家已实现）
- [x] Phase 3: CLI 集成（/providers, /provider, /models 增强）
- [x] Phase 4: 高级功能（成本追踪、故障转移、自动路由）
- [x] Phase 5: 完整厂商接入（新增 25 家，总计 46 家）

### 已实现厂商 (46 家)

| 类型 | 厂商数量 | 厂商列表 |
|------|----------|----------|
| 国际主流 | 5 | OpenAI, Anthropic, Google Gemini, Mistral, Cohere |
| 云厂商 | 5 | Azure OpenAI, Google Vertex AI, AWS Bedrock, AWS SageMaker, 腾讯云 |
| NVIDIA | 3 | NVIDIA NIM, NVIDIA Triton, NVIDIA Catalog |
| 国内厂商 | 15 | DeepSeek, 月之暗面, 智谱, 通义千问, 文心一言, 百川, MiniMax, 讯飞, 腾讯混元, 阶跃星辰, 魔搭社区, 百度千帆, 阿里云 PAI, 腾讯云 TI, 七牛云 |
| 推理平台 | 13 | Ollama, Groq, Together.ai, OpenRouter, 硅基流动, Replicate, Hugging Face, Lepton, novita.ai, Jina, GPUStack, PerfXCloud, Xorbits |
| 本地部署 | 4 | LocalAI, Xinference, OpenLLM, Text Embedding |
| 基础 | 1 | OpenAI Compatible |

### 高级功能模块

| 模块 | 文件 | 功能 |
|------|------|------|
| 成本追踪 | `cost_tracker.py` | Token 消耗记录、费用计算、按厂商/模型统计 |
| 故障转移 | `failover.py` | 自动切换备用厂商、健康检查、重试策略 |
| 自动路由 | `auto_router.py` | 根据任务类型选择最佳模型、优先级策略 |

