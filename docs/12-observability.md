# 12｜可观测性（Logging / Metrics / Tracing / Profiling）

目标：让系统"可调试、可评估、可审计"，并能定位失败原因与性能瓶颈。

---

## 1. 日志（Logging）

### 1.1 日志类型
- **交互日志**：用户输入、模型输出（可选脱敏）、会话摘要
- **工具日志**：ToolCallRequest/Result（结构化）
- **系统日志**：异常、超时、资源占用

### 1.2 结构化字段（统一规范）
- `timestamp`：时间戳
- `trace_id`：贯穿一次任务
- `session_id`：会话 ID
- `plan_id`：计划 ID
- `tool_call_id`：工具调用 ID
- `level`：日志级别
- `event`：事件类型
- `duration_ms`：持续时间（毫秒）

### 1.3 脱敏与采样
- 默认脱敏：token/key/password
- 对大输出采用采样/截断，但必须保留"错误尾部"

### 1.4 实现位置
- `src/clude_code/observability/logger.py`：统一日志系统
- `src/clude_code/observability/audit.py`：审计日志
- `src/clude_code/observability/trace.py`：追踪日志

---

## 2. 指标（Metrics）

### 2.1 关键指标

#### 系统指标
| 指标名称 | 类型 | 说明 |
|---------|------|------|
| `system_cpu_percent` | Gauge | CPU 使用率 (%) |
| `system_memory_percent` | Gauge | 内存使用率 (%) |
| `system_memory_bytes` | Gauge | 内存使用量 (used/total) |
| `system_disk_percent` | Gauge | 磁盘使用率 (%) |
| `system_disk_bytes` | Gauge | 磁盘使用量 (used/total) |
| `system_network_bytes` | Counter | 网络流量 (sent/recv) |

#### LLM 指标
| 指标名称 | 类型 | 说明 |
|---------|------|------|
| `llm_requests_total` | Counter | LLM 请求总数 |
| `llm_request_duration_seconds` | Histogram | LLM 请求耗时分布 |
| `llm_tokens_used_total` | Counter | LLM Token 使用总数 |
| `llm_cache_hits_total` | Counter | LLM 缓存命中次数 |
| `llm_cache_misses_total` | Counter | LLM 缓存未命中次数 |

#### 工具调用指标
| 指标名称 | 类型 | 说明 |
|---------|------|------|
| `tool_calls_total` | Counter | 工具调用总数 (按工具类型标签) |
| `tool_call_duration_seconds` | Histogram | 工具调用耗时分布 |
| `tool_call_errors_total` | Counter | 工具调用错误总数 |

#### 任务执行指标
| 指标名称 | 类型 | 说明 |
|---------|------|------|
| `task_executions_total` | Counter | 任务执行总数 |
| `task_execution_duration_seconds` | Histogram | 任务执行耗时分布 |

#### 会话指标
| 指标名称 | 类型 | 说明 |
|---------|------|------|
| `active_sessions` | Gauge | 活跃会话数 |
| `sessions_total` | Counter | 会话总数 |

### 2.2 分布与标签
- `workspace_size_bucket`：工作区大小分桶
- `project_type`：项目类型
- `tool_name`：工具名称
- `error_code`：错误代码
- `operation`：操作类型（读/写）
- `file_type`：文件类型（regular/patch）
- `task_type`：任务类型
- `status`：状态（success/error）

### 2.3 指标类型说明
- **Counter**：计数器，只增不减，用于统计次数
- **Gauge**：仪表盘，可增可减，用于表示当前值
- **Histogram**：直方图，记录分布，支持分桶统计
- **Summary**：摘要，记录统计信息和分位数

### 2.4 实现位置
- `src/clude_code/observability/metrics.py`：指标定义和收集
- `src/clude_code/observability/metrics_storage.py`：指标存储和导出

---

## 3. 链路追踪（Tracing）

### 3.1 Span 建模

```
task.run (根 Span)
├── context.build
├── plan.generate
├── llm_request
├── tool.call:<name> (多次)
│   ├── read_file
│   ├── write_file
│   ├── grep
│   └── run_cmd
└── verify.run
```

### 3.2 Span 属性
- `trace_id`：追踪 ID（跨整个请求）
- `span_id`：Span ID（当前操作）
- `parent_span_id`：父 Span ID
- `name`：Span 名称
- `kind`：Span 类型（INTERNAL/SERVER/CLIENT/PRODUCER/CONSUMER）
- `attributes`：属性键值对
- `events`：事件列表
- `status`：状态（OK/ERROR/CANCELLED）

### 3.3 追踪采样
- 支持基于概率的采样（默认 10%）
- 可配置采样率：`observability.tracing.sampling_rate`
- 采样以 Trace 为单位，避免同一请求数据不完整

### 3.4 追踪导出
- **文件导出**：JSONL 格式存储到 `.clude/traces/traces.jsonl`
- **控制台导出**：实时输出到控制台
- **批量导出**：累积后批量写入，减少 I/O

### 3.5 实现位置
- `src/clude_code/observability/tracing.py`：追踪系统核心实现

---

## 4. 性能分析（Profiling）

### 4.1 分析类型

#### CPU 分析
- 基于 py-spy 的 CPU 性能分析
- 收集 CPU 使用率和频率信息
- 支持采样配置

#### 内存分析
- 基于 memory_profiler 的内存分析
- 收集进程内存使用情况
- 支持内存增量统计

#### I/O 分析
- 基于 psutil 的 I/O 分析
- 收集磁盘读写和网络 I/O
- 支持 I/O 增量统计

#### 函数分析
- 基于 cProfile 的函数级分析
- 收集函数调用统计信息
- 支持 top N 热点函数展示

### 4.2 使用方式

#### 装饰器方式
```python
from clude_code.observability.profiler import profile, ProfileType

@profile("my_function", ProfileType.FUNCTION)
def my_function():
    # 函数实现
    pass
```

#### 上下文管理器方式
```python
from clude_code.observability.profiler import profile_context, ProfileType

with profile_context("critical_section", ProfileType.CPU):
    # 代码块
    pass
```

#### 手动方式
```python
from clude_code.observability.profiler import get_profile_manager, ProfileType

manager = get_profile_manager(".")
manager.start_profiling("operation_name", ProfileType.CPU)
# 执行代码
record = manager.stop_profiling(ProfileType.CPU)
```

### 4.3 实现位置
- `src/clude_code/observability/profiler.py`：性能分析器实现

---

## 5. 回放（Replay）

### 5.1 记录内容
- 用户输入
- ContextPack
- 模型输出（含工具调用指令）
- 工具调用的请求/结果
- 文件变更 patch/diff

### 5.2 回放用途
- 复现 bug
- 回归评测
- 审计取证

### 5.3 实现位置
- `src/clude_code/observability/audit.py`：审计日志
- `src/clude_code/observability/trace.py`：追踪日志

---

## 6. CLI 命令

### 6.1 指标命令
```bash
# 查看指标状态
clude observability metrics --hours 1

# 导出指标
clude observability export --format prometheus --hours 24
```

### 6.2 追踪命令
```bash
# 查看追踪数据
clude observability traces --limit 50
```

### 6.3 性能分析命令
```bash
# 查看性能分析
clude observability profiles --type function
clude observability profiles --type cpu
clude observability profiles --type memory
clude observability profiles --type io
```

### 6.4 清理命令
```bash
# 清理过期数据
clude observability cleanup --days 7
```

### 6.5 仪表板命令
```bash
# 显示可观测性仪表板
clude observability dashboard
```

### 6.6 实现位置
- `src/clude_code/cli/observability_cli.py`：CLI 命令实现

---

## 7. 集成使用

### 7.1 可观测性管理器
```python
from clude_code.observability.integration import get_observability_manager

obs_manager = get_observability_manager(cfg)

# 记录 LLM 请求
obs_manager.record_llm_request(
    duration=1.23,
    tokens_used=150,
    cache_hit=False
)

# 记录工具调用
obs_manager.record_tool_call(
    tool_name="read_file",
    duration=0.45,
    success=True,
    file_size=1024
)

# 记录任务执行
obs_manager.record_task_execution(
    task_type="data_processing",
    duration=2.34,
    success=True
)
```

### 7.2 装饰器集成
```python
from clude_code.observability.integration import (
    observe_llm_request,
    observe_tool_call,
    observe_task_execution
)

class MyLLMClient:
    @observe_llm_request
    def chat(self, messages):
        # 自动记录 LLM 请求指标和追踪
        pass

class MyTools:
    @observe_tool_call("read_file")
    def read_file(self, path):
        # 自动记录工具调用指标和追踪
        pass
```

### 7.3 实现位置
- `src/clude_code/observability/integration.py`：集成层实现

---

## 8. 配置文件

### 8.1 指标配置
```toml
[observability.metrics]
enabled = true
collection_interval = 10  # 秒
storage_backend = "file"  # memory, file, remote
retention_hours = 168  # 7天
max_file_size_mb = 100
```

### 8.2 追踪配置
```toml
[observability.tracing]
enabled = true
sampling_rate = 0.1  # 10%
exporter = "file"  # file, console, remote
batch_size = 100
export_interval = 5  # 秒
```

### 8.3 性能分析配置
```toml
[observability.profiling]
enabled = false  # 默认关闭，按需开启
cpu_profiling = true
memory_profiling = true
io_profiling = false
function_profiling = true
```

---

## 9. 数据存储位置

| 数据类型 | 存储位置 |
|---------|---------|
| 指标数据 | `{workspace}/.clude/metrics/data.jsonl` |
| 追踪数据 | `{workspace}/.clude/traces/traces.jsonl` |
| 性能分析 | `{workspace}/.clude/profiles/` |
| 审计日志 | `{workspace}/.clude/logs/audit.jsonl` |
| 追踪日志 | `{workspace}/.clude/logs/trace.jsonl` |
| 应用日志 | `{workspace}/.clude/logs/app.log` |

---

## 10. MVP 实现建议

- ✅ **已实现**：结构化工具日志 + trace_id
- ✅ **已实现**：回放包导出（JSONL 格式）
- ✅ **已实现**：指标面板（CLI + 存储）
- ✅ **已实现**：分布式追踪（Span/Trace）
- ✅ **已实现**：性能分析器（CPU/内存/I/O/函数）
- 🔄 **进行中**：自动评测集成
- ⏳ **待实现**：可视化面板（Web UI）

---

## 11. 参考资料

- [OpenTelemetry](https://opentelemetry.io/)：分布式追踪标准
- [Prometheus](https://prometheus.io/)：指标收集和存储
- [py-spy](https://github.com/benfred/py-spy)：CPU 性能分析
- [memory-profiler](https://github.com/pythonprofilers/memory_profiler)：内存性能分析
- [psutil](https://github.com/giampaolo/psutil)：系统资源监控
