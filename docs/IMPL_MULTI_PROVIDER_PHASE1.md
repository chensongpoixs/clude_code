# Phase 1: 多厂商基础架构实现

## 1.1 抽象基类 LLMProvider

### 思考过程

1. **职责定义**
   - 定义所有 LLM 厂商必须实现的统一接口
   - 包含同步/异步/流式三种调用方式
   - 提供模型信息查询能力

2. **数据模型设计**
   - `ModelInfo`: 模型元信息（ID、名称、上下文窗口、能力标记）
   - `ProviderConfig`: 厂商配置（API Key、Base URL、额外参数）
   - `ChatMessage`: 复用现有定义

3. **接口设计原则**
   - 最小接口原则：只定义必要的抽象方法
   - 提供默认实现：验证、测试连接等通用逻辑
   - 支持扩展：通过 `**kwargs` 传递厂商特定参数

4. **文件位置**
   - `src/clude_code/llm/base.py`

### 实现要点

```python
# 核心抽象方法
- chat(messages, **kwargs) -> str           # 同步聊天
- chat_async(messages, **kwargs) -> str     # 异步聊天  
- chat_stream(messages, **kwargs) -> Iterator[str]  # 流式
- list_models() -> list[ModelInfo]          # 模型列表
- get_model_info(model_id) -> ModelInfo     # 单模型信息

# 可选方法（带默认实现）
- validate_config() -> tuple[bool, str]     # 配置验证
- test_connection() -> tuple[bool, str]     # 连接测试
```

### 状态
- [x] 思考过程
- [x] 代码实现
- [x] 测试验证

---

## 1.2 厂商注册表 ProviderRegistry

### 思考过程

1. **设计模式**
   - 单例模式：全局唯一注册表
   - 装饰器注册：`@ProviderRegistry.register("openai")`
   - 延迟实例化：按需创建厂商实例

2. **核心功能**
   - 注册厂商类
   - 获取厂商实例（带缓存）
   - 列出所有已注册厂商

3. **实例管理**
   - 使用 `{provider_name}:{config_hash}` 作为缓存键
   - 支持同一厂商多配置（如多个 OpenAI 账号）

4. **文件位置**
   - `src/clude_code/llm/registry.py`

### 状态
- [x] 思考过程
- [x] 代码实现
- [x] 测试验证

---

## 1.3 配置数据模型 ProvidersConfig

### 思考过程

1. **配置结构**
   ```yaml
   providers:
     default: openai
     openai:
       enabled: true
       api_key: ${OPENAI_API_KEY}
       base_url: https://api.openai.com/v1
       default_model: gpt-4o
   ```

2. **环境变量支持**
   - 使用 `${VAR_NAME}` 语法
   - 在加载时自动展开

3. **向后兼容**
   - 保留原有 `LLMConfig` 作为单厂商简化配置
   - 新增 `ProvidersConfig` 支持多厂商

4. **文件位置**
   - 扩展 `src/clude_code/config/config.py`

### 状态
- [x] 思考过程
- [x] 代码实现
- [x] 测试验证

---

## 1.4 重构 ModelManager

### 思考过程

1. **职责扩展**
   - 原有：管理单一 LLM 客户端
   - 新增：管理多个厂商实例

2. **核心变更**
   - 添加 `_current_provider: str` 跟踪当前厂商
   - 添加 `switch_provider(name)` 切换厂商
   - 修改 `list_models()` 返回当前厂商的模型

3. **兼容性**
   - 保留现有 API（`switch_model`, `get_current_model`）
   - 新增厂商相关 API

4. **文件位置**
   - 修改 `src/clude_code/llm/model_manager.py`

### 状态
- [x] 思考过程
- [x] 代码实现
- [x] 测试验证

---

## 实施顺序

1. ✅ 写思考过程（本文件）
2. ✅ 实现 `base.py`
3. ✅ 实现 `registry.py`
4. ✅ 扩展 `config.py`
5. ✅ 重构 `model_manager.py`
6. ✅ 编译检查
7. ✅ 汇报进度

---

## Phase 1 完成汇报

### 新增文件
| 文件 | 行数 | 功能 |
|------|------|------|
| `llm/base.py` | ~220 | 抽象基类 `LLMProvider`, `ModelInfo`, `ProviderConfig` |
| `llm/registry.py` | ~140 | 厂商注册表 `ProviderRegistry` |
| `llm/providers/__init__.py` | ~40 | 厂商模块自动加载 |
| `llm/providers/openai_compat.py` | ~180 | 通用 OpenAI 兼容厂商 |

### 修改文件
| 文件 | 变更 |
|------|------|
| `config/config.py` | 新增 `ProviderConfigItem`, `ProvidersConfig` |
| `llm/__init__.py` | 导出新模块 |
| `llm/model_manager.py` | 支持多厂商管理 |

### 验证结果
```bash
# 编译检查
python -m compileall -q src/clude_code/llm/*.py  # ✅ 通过

# 导入测试
from clude_code.llm import LLMProvider, ProviderRegistry, list_providers  # ✅ 成功

# 配置测试
cfg.providers.default  # ✅ 返回 "openai_compat"

# 厂商注册测试
mm.register_provider('test', provider)  # ✅ 成功
mm.list_providers()  # ✅ 返回厂商列表
```

