# 可观测性模块

负责记录 Agent 的全量行为日志，包括审计日志、调试轨迹、性能指标、分布式追踪和性能分析。

## 核心组件

### 日志与审计
- `audit.py`: 记录关键行为（工具调用、修改操作）的 JSONL 审计日志。
- `trace.py`: 记录详细的执行轨迹，用于问题复现与流程分析。
- `logger.py`: **统一日志系统**（带文件名和行号，支持 Rich markup）

### 性能监控
- `metrics.py`: 性能指标收集系统，支持 Counter、Gauge、Histogram 和 Summary 四种指标类型。
- `metrics_storage.py`: 指标存储和导出，支持内存存储、文件存储和多种导出格式（Prometheus、JSON）。

### 分布式追踪
- `tracing.py`: 基于 OpenTelemetry 标准的分布式追踪系统，支持 Span、Trace、Context 传播。

### 性能分析
- `profiler.py`: 性能分析工具，支持 CPU、内存、I/O 和函数级性能分析。

### 集成
- `integration.py`: 可观测性集成层，提供统一的业务指标收集和便捷的装饰器。

## 性能监控指标

### 基本用法

```python
from clude_code.observability.metrics import get_metrics_collector

# 获取指标收集器
metrics = get_metrics_collector(".")

# 创建或获取计数器
counter = metrics.counter("requests_total", "Total number of requests")
counter.inc()  # 增加计数

# 创建或获取直方图
histogram = metrics.histogram(
    "request_duration_seconds",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0],
    help_text="Request duration in seconds"
)
histogram.observe(0.5)  # 记录观察值

# 创建或获取仪表盘
gauge = metrics.gauge("active_connections", "Number of active connections")
gauge.set(10)  # 设置值
gauge.inc()    # 增加
gauge.dec()    # 减少

# 创建或获取摘要
summary = metrics.summary(
    "request_latency",
    quantiles=[0.5, 0.9, 0.99],
    help_text="Request latency summary"
)
summary.observe(0.3)
```

### 收集所有指标

```python
from clude_code.observability.metrics import get_metrics_collector

metrics = get_metrics_collector(".")

# 收集所有指标数据点
points = metrics.collect_all()

# 打印指标
for point in points:
    print(f"{point.name}: {point.value}")
```

### 系统指标

系统指标会自动收集，包括：

- `system_cpu_percent`: CPU 使用率 (%)
- `system_memory_percent`: 内存使用率 (%)
- `system_memory_bytes`: 内存使用量 (used/total)
- `system_disk_percent`: 磁盘使用率 (%)
- `system_disk_bytes`: 磁盘使用量 (used/total)
- `system_network_bytes`: 网络流量 (sent/recv)

## 指标存储与导出

### 基本用法

```python
from clude_code.observability.metrics_storage import get_metrics_manager, StorageBackend

# 获取指标管理器
manager = get_metrics_manager(
    workspace_root=".",
    storage_backend=StorageBackend.FILE,
    storage_options={"max_file_size_mb": 50}
)

# 存储指标
from clude_code.observability.metrics import MetricPoint, MetricType
points = [
    MetricPoint(
        name="custom_metric",
        metric_type=MetricType.COUNTER,
        value=1,
        timestamp=time.time()
    )
]
manager.store(points)

# 查询指标
query = MetricsQuery(name="custom_metric", start_time=time.time() - 3600)
results = manager.query(query)

# 导出为 Prometheus 格式
prometheus_output = manager.export(format="prometheus")

# 导出为 JSON 格式
json_output = manager.export(format="json")
```

### 获取指标名称

```python
metric_names = manager.get_metric_names()
print("Available metrics:", metric_names)
```

### 清理过期数据

```python
# 清理7天前的数据
removed_count = manager.cleanup(retention_hours=168)
print(f"Removed {removed_count} expired metric points")
```

## 分布式追踪

### 基本用法

```python
from clude_code.observability.tracing import get_tracer, SpanKind

# 获取追踪器
tracer = get_tracer("my_component")

# 创建 Span
with tracer.start_as_current_span("operation_name", SpanKind.CLIENT) as span:
    span.set_attribute("user_id", "12345")
    span.add_event("start_processing")
    
    # 执行操作
    result = perform_operation()
    
    span.add_event("finished_processing")
    span.set_status(StatusCode.OK)
```

### 追踪装饰器

```python
from clude_code.observability.tracing import trace_span, SpanKind

@trace_span("my_function", SpanKind.INTERNAL)
def my_function(arg1, arg2):
    # 函数实现
    # 自动创建和管理 Span
    pass
```

### 追踪装饰器类方法

```python
from clude_code.observability.tracing import trace_method

class MyService:
    @trace_method(name="process_data", kind=SpanKind.SERVER)
    def process_data(self, data):
        # 方法实现
        pass
```

### 状态码

```python
from clude_code.observability.tracing import StatusCode

span.set_status(StatusCode.OK)       # 成功
span.set_status(StatusCode.ERROR, "错误信息")  # 错误
span.set_status(StatusCode.CANCELLED)  # 取消
```

## 性能分析

### 基本用法

```python
from clude_code.observability.profiler import get_profile_manager, ProfileType

# 获取分析管理器
manager = get_profile_manager(".")

# 开始性能分析
manager.start_profiling("my_operation", ProfileType.FUNCTION)

# 执行代码
result = perform_operation()

# 停止性能分析
record = manager.stop_profiling(ProfileType.FUNCTION)
print(f"Duration: {record.duration} seconds")
```

### 装饰器用法

```python
from clude_code.observability.profiler import profile, ProfileType

@profile("my_function", ProfileType.FUNCTION)
def my_function():
    # 函数实现
    # 自动进行性能分析
    pass
```

### 上下文管理器用法

```python
from clude_code.observability.profiler import profile_context, ProfileType

with profile_context("critical_section", ProfileType.CPU):
    # 代码块
    # 自动进行 CPU 性能分析
    pass
```

### 分析类型

```python
from clude_code.observability.profiler import ProfileType

# CPU 性能分析
manager.start_profiling("cpu_operation", ProfileType.CPU)

# 内存性能分析
manager.start_profiling("memory_operation", ProfileType.MEMORY)

# I/O 性能分析
manager.start_profiling("io_operation", ProfileType.IO)

# 函数性能分析
manager.start_profiling("function_operation", ProfileType.FUNCTION)
```

### 获取分析记录

```python
# 获取所有分析记录
records = manager.get_records()

# 获取特定类型的记录
cpu_records = manager.get_records(ProfileType.CPU)

# 限制数量
recent_records = manager.get_records(limit=10)

# 保存到文件
manager.save_records()

# 清除记录
manager.clear_records()
```

## 集成使用

### 可观测性管理器

```python
from clude_code.observability.integration import get_observability_manager
from clude_code.config import CludeConfig

# 创建配置
cfg = CludeConfig()

# 获取可观测性管理器
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

# 获取指标摘要
summary = obs_manager.get_metrics_summary(hours=1)
print(f"LLM requests: {summary['llm_requests']}")
print(f"Tool calls: {summary['tool_calls']}")

# 导出指标
prometheus_data = obs_manager.export_metrics(format="prometheus", hours=1)
```

### 装饰器集成

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

class MyTasks:
    @observe_task_execution("data_processing")
    def process_data(self, data):
        # 自动记录任务执行指标和追踪
        pass
```

## CLI 命令

### 查看指标状态

```bash
# 查看过去1小时的指标
clude observability metrics --hours 1

# 查看过去24小时的指标
clude observability metrics --hours 24

# 指定工作区
clude observability metrics --hours 1 --workspace /path/to/workspace
```

### 查看追踪数据

```bash
# 查看最近50条追踪
clude observability traces --limit 50

# 查看最近100条追踪
clude observability traces --limit 100
```

### 查看性能分析

```bash
# 查看函数性能分析
clude observability profiles --type function

# 查看 CPU 性能分析
clude observability profiles --type cpu

# 查看内存性能分析
clude observability profiles --type memory

# 查看 I/O 性能分析
clude observability profiles --type io
```

### 导出指标数据

```bash
# 导出 Prometheus 格式
clude observability export --format prometheus --hours 1

# 导出 JSON 格式
clude observability export --format json --hours 24

# 导出到文件
clude observability export --format prometheus --hours 1 --output metrics.prom
```

### 清理过期数据

```bash
# 清理7天前的数据
clude observability cleanup --days 7

# 清理30天前的数据
clude observability cleanup --days 30
```

### 查看仪表板

```bash
# 显示可观测性仪表板
clude observability dashboard
```

## 日志系统使用

### 基本用法

```python
from clude_code.observability.logger import get_logger

logger = get_logger(__name__)
logger.info("这是一条信息日志")
logger.warning("这是一条警告日志")
logger.error("这是一条错误日志")
```

### 快捷函数

```python
from clude_code.observability.logger import info, warning, error

info("快速信息日志")
warning("快速警告日志")
error("快速错误日志")
```

### 日志格式

所有日志输出格式为：`[文件名:行号] 日志级别 - 消息内容`

例如：
```
[main.py:48] INFO - 进入 clude chat（llama.cpp HTTP）
[main.py:680] ERROR - workspace_root 不存在
```

### 支持 Rich Markup

日志系统支持 Rich 的 markup 语法，可以添加颜色和样式：

```python
logger.info("[bold]重要信息[/bold]")
logger.error("[red]错误信息[/red]")
logger.warning("[yellow]警告信息[/yellow]")
```

## 模块流程

![Observability Flow](module_flow.svg)

## 文件存储位置

### 指标数据
- 位置: `{workspace}/.clude/metrics/data.jsonl`
- 索引: `{workspace}/.clude/metrics/index.json`

### 追踪数据
- 位置: `{workspace}/.clude/traces/traces.jsonl`

### 性能分析数据
- 位置: `{workspace}/.clude/profiles/`

### 审计日志
- 位置: `{workspace}/.clude/logs/audit.jsonl`

### 追踪日志
- 位置: `{workspace}/.clude/logs/trace.jsonl`

### 应用日志
- 位置: `{workspace}/.clude/logs/app.log`
