# Phase 4: 高级功能 - 成本追踪、故障转移、自动路由

## 目标

实现三个高级功能：
1. **成本追踪**：记录每次调用的 token 消耗和费用
2. **故障转移**：当一个厂商失败时自动切换到备用厂商
3. **自动路由**：根据任务类型自动选择最合适的模型

## 思考过程

### 4.1 成本追踪模块 (CostTracker)

**需求分析**：
- 记录每次 LLM 调用的 token 消耗（输入/输出）
- 根据厂商定价计算费用
- 提供会话级和全局级统计
- 支持 `/cost` 命令查看

**数据模型**：
```python
@dataclass
class UsageRecord:
    timestamp: datetime
    provider_id: str
    model_id: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    latency_ms: int
```

**核心功能**：
- `record_usage()`: 记录一次调用
- `get_session_cost()`: 获取会话总费用
- `get_provider_cost()`: 按厂商统计
- `get_model_cost()`: 按模型统计

### 4.2 故障转移模块 (Failover)

**需求分析**：
- 当主厂商请求失败时，自动切换到备用厂商
- 支持配置优先级列表
- 记录失败原因和切换历史
- 支持健康检查

**配置示例**：
```yaml
failover:
  enabled: true
  max_retries: 2
  fallback_chain:
    - deepseek
    - siliconflow
    - openai_compat
```

**核心逻辑**：
```python
def chat_with_failover(messages, **kwargs):
    for provider_id in fallback_chain:
        try:
            return provider.chat(messages, **kwargs)
        except Exception as e:
            log_failure(provider_id, e)
            continue
    raise AllProvidersFailedError()
```

### 4.3 自动路由模块 (AutoRouter)

**需求分析**：
- 根据任务类型选择最合适的模型
- 考虑因素：成本、速度、能力（Vision/Code）
- 支持用户偏好覆盖

**路由策略**：
| 任务类型 | 推荐模型 | 原因 |
|----------|----------|------|
| 代码生成 | DeepSeek Coder / GPT-4o | 代码能力强 |
| 图片分析 | GPT-4o / Claude 3.5 | Vision 支持 |
| 快速问答 | GPT-4o-mini / DeepSeek Chat | 低成本高速 |
| 复杂推理 | o1 / DeepSeek R1 | 推理能力强 |
| 长文档 | Claude 3.5 / Gemini 1.5 | 大上下文 |

**路由逻辑**：
```python
def select_model(task_type: str, context_length: int, has_image: bool) -> str:
    if has_image:
        return "gpt-4o"  # Vision 支持
    if context_length > 100000:
        return "claude-3-5-sonnet"  # 大上下文
    if task_type == "coding":
        return "deepseek-coder"  # 代码专精
    return "deepseek-chat"  # 默认
```

## 文件规划

| 文件 | 功能 |
|------|------|
| `llm/cost_tracker.py` | 成本追踪 |
| `llm/failover.py` | 故障转移 |
| `llm/auto_router.py` | 自动路由 |
| `config/config.py` | 新增配置项 |

## 实施步骤

1. ✅ 写思路文档（本文件）
2. ✅ 实现成本追踪模块
3. ✅ 实现故障转移模块
4. ✅ 实现自动路由模块
5. ✅ 集成到 __init__.py
6. ✅ 编译检查
7. ✅ 汇报进度

---

## 完成汇报

### 新增文件

| 文件 | 行数 | 功能 |
|------|------|------|
| `llm/cost_tracker.py` | ~280 | 成本追踪：记录 token 消耗、计算费用、按厂商/模型统计 |
| `llm/failover.py` | ~280 | 故障转移：自动切换备用厂商、健康检查、重试策略 |
| `llm/auto_router.py` | ~320 | 自动路由：根据任务类型选择最佳模型、优先级策略 |

### 核心功能

#### 成本追踪 (CostTracker)
```python
tracker = CostTracker()
tracker.record_usage("deepseek", "deepseek-chat", 1000, 500, 1200)
summary = tracker.get_summary()
# total_cost_usd=0.00028, by_provider={'deepseek': {...}}
```

#### 故障转移 (FailoverManager)
```python
failover = FailoverManager(FailoverConfig(
    fallback_chain=["deepseek", "siliconflow", "openai"],
    max_retries=2,
))
result = failover.chat_with_failover(messages)  # 自动切换
```

#### 自动路由 (AutoRouter)
```python
decision = auto_select_model(TaskType.CODING)
# provider_id="deepseek", model_id="deepseek-coder"

decision = auto_select_model(TaskType.VISION, has_image=True)
# provider_id="openai", model_id="gpt-4o"
```

### 验证结果

```bash
# 编译检查
python -m compileall -q src/clude_code/llm/*.py  # ✅ 通过

# 导入测试
from clude_code.llm import CostTracker, FailoverManager, AutoRouter  # ✅ 成功

# 功能测试
tracker.record_usage(...)  # ✅ 成本计算正确
auto_select_model(TaskType.CODING)  # ✅ 路由决策正确

# Lint 检查
read_lints  # ✅ 无错误
```

