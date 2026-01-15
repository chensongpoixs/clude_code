# clude-code 可观测性增强实现指南

## 概述

本文档介绍了 clude-code 项目中实现的可观测性增强功能，包括性能监控指标、分布式追踪和性能分析工具的详细使用方法。

## 实现的功能

### 1. 性能监控指标系统

我们实现了一个全面的指标收集和存储系统：

- **指标类型**：支持计数器(Counter)、仪表盘(Gauge)、直方图(Histogram)和摘要(Summary)
- **存储后端**：支持内存和文件存储，可扩展远程存储
- **导出格式**：支持 Prometheus 和 JSON 格式导出
- **自动收集**：自动收集系统指标(CPU、内存、磁盘、网络)

### 2. 分布式追踪系统

基于 OpenTelemetry 标准实现了分布式追踪功能：

- **Span 模型**：表示操作的基本单元，支持父子关系
- **Trace 模型**：表示一个完整的请求流程
- **导出器**：支持文件、控制台和批量导出
- **采样机制**：支持基于概率的采样，减少性能影响

### 3. 性能分析工具

实现了多种类型的性能分析器：

- **CPU 分析器**：基于 py-spy 的 CPU 性能分析
- **内存分析器**：基于 memory_profiler 的内存使用分析
- **I/O 分析器**：基于 psutil 的 I/O 性能分析
- **函数分析器**：基于 cProfile 的函数级性能分析

### 4. 可观测性集成

提供了一个统一的集成层，简化使用：

- **业务指标**：预定义的 LLM、工具调用和任务执行指标
- **装饰器**：简化函数和方法的可观测性集成
- **CLI 工具**：提供查询和管理可观测性数据的命令行接口

## 使用方法

### 1. 基本使用

#### 1.1 初始化可观测性管理器

```python
from clude_code.config import CludeConfig
from clude_code.observability.integration import get_observability_manager

# 创建配置
cfg = CludeConfig()

# 获取可观测性管理器
obs_manager = get_observability_manager(cfg)
```

#### 1.2 记录业务指标

```python
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
    task_type="file_processing",
    duration=2.34,
    success=True
)
```

#### 1.3 使用性能分析

```python
# 开始性能分析
obs_manager.start_profiling("my_function", ProfileType.FUNCTION)

# 执行代码
result = my_function()

# 停止性能分析
profile_record = obs_manager.stop_profiling(ProfileType.FUNCTION)
print(f"Function duration: {profile_record.duration}")
```

### 2. 使用装饰器

#### 2.1 LLM 请求观察

```python
from clude_code.observability.integration import observe_llm_request

class MyLLMClient:
    def __init__(self, cfg):
        self.cfg = cfg
    
    @observe_llm_request
    def chat(self, messages):
        # LLM 请求实现
        # 自动记录请求时间、token 使用量等
        pass
```

#### 2.2 工具调用观察

```python
from clude_code.observability.integration import observe_tool_call

class MyTool:
    def __init__(self, cfg):
        self.cfg = cfg
    
    @observe_tool_call("read_file")
    def read_file(self, path):
        # 工具实现
        # 自动记录调用时间、成功率、文件大小等
        pass
```

#### 2.3 任务执行观察

```python
from clude_code.observability.integration import observe_task_execution

class MyTask:
    def __init__(self, cfg):
        self.cfg = cfg
    
    @observe_task_execution("data_processing")
    def process_data(self, data):
        # 任务实现
        # 自动记录执行时间、成功率等
        pass
```

### 3. 使用分布式追踪

#### 3.1 手动追踪

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
    span.set_status("OK")
```

#### 3.2 使用装饰器

```python
from clude_code.observability.tracing import trace_span, SpanKind

@trace_span("my_function", SpanKind.INTERNAL)
def my_function(arg1, arg2):
    # 函数实现
    # 自动创建和管理 Span
    pass
```

### 4. 使用性能分析器

#### 4.1 使用装饰器

```python
from clude_code.observability.profiler import profile, ProfileType

@profile("my_function", ProfileType.FUNCTION)
def my_function():
    # 函数实现
    # 自动进行性能分析
    pass
```

#### 4.2 使用上下文管理器

```python
from clude_code.observability.profiler import profile_context, ProfileType

def my_function():
    with profile_context("critical_section", ProfileType.CPU):
        # 代码块
        # 自动进行 CPU 性能分析
        pass
```

### 5. 使用 CLI 工具

#### 5.1 查看指标状态

```bash
# 查看过去1小时的指标
clude observability metrics --hours 1

# 查看过去24小时的指标
clude observability metrics --hours 24
```

#### 5.2 查看追踪数据

```bash
# 查看最近50条追踪
clude observability traces --limit 50

# 查看最近100条追踪
clude observability traces --limit 100
```

#### 5.3 查看性能分析

```bash
# 查看函数性能分析
clude observability profiles --type function

# 查看 CPU 性能分析
clude observability profiles --type cpu

# 查看内存性能分析
clude observability profiles --type memory
```

#### 5.4 导出指标数据

```bash
# 导出 Prometheus 格式
clude observability export --format prometheus --hours 1

# 导出 JSON 格式到文件
clude observability export --format json --hours 24 --output metrics.json
```

#### 5.5 清理过期数据

```bash
# 清理7天前的数据
clude observability cleanup --days 7

# 清理30天前的数据
clude observability cleanup --days 30
```

#### 5.6 查看仪表板

```bash
# 显示可观测性仪表板
clude observability dashboard
```

## 集成到现有系统

### 1. 集成到 AgentLoop

```python
from clude_code.observability.integration import get_observability_manager

class EnhancedAgentLoop(AgentLoop):
    def __init__(self, cfg):
        super().__init__(cfg)
        self.obs_manager = get_observability_manager(cfg)
    
    def run_turn(self, user_text, *, confirm, debug=False):
        # 开始会话
        session_id = f"sess_{int(time.time())}"
        self.obs_manager.start_session(session_id)
        
        try:
            # 执行原有的逻辑
            result = super().run_turn(user_text, confirm=confirm, debug=debug)
            return result
        finally:
            # 结束会话
            self.obs_manager.end_session(session_id)
```

### 2. 集成到工具实现

```python
from clude_code.observability.integration import observe_tool_call

class LocalTools:
    @observe_tool_call("read_file")
    def read_file(self, path):
        # 原有实现
        # 自动记录工具调用指标和追踪
        pass
```

### 3. 集成到 LLM 客户端

```python
from clude_code.observability.integration import observe_llm_request

class StreamingLLMClient:
    @observe_llm_request
    def chat(self, messages):
        # 原有实现
        # 自动记录 LLM 请求指标
        pass
```

## 配置选项

### 1. 指标配置

```python
# 在配置文件中添加
[observability.metrics]
enabled = true
collection_interval = 10  # 秒
storage_backend = "file"  # memory, file, remote
retention_hours = 168  # 7天
max_file_size_mb = 100
```

### 2. 追踪配置

```python
# 在配置文件中添加
[observability.tracing]
enabled = true
sampling_rate = 0.1  # 10%
exporter = "file"  # file, console, remote
batch_size = 100
export_interval = 5  # 秒
```

### 3. 性能分析配置

```python
# 在配置文件中添加
[observability.profiling]
enabled = false  # 默认关闭，按需开启
cpu_profiling = true
memory_profiling = true
io_profiling = false
function_profiling = true
```

## 最佳实践

### 1. 指标设计

- 使用有意义的指标名称和标签
- 避免高基数标签（如用户ID）
- 为指标添加帮助文本
- 选择合适的指标类型（Counter、Gauge、Histogram、Summary）

### 2. 追踪设计

- 为关键操作创建 Span
- 添加有意义的属性和事件
- 使用适当的 Span 类型
- 保持 Span 层级结构合理

### 3. 性能分析

- 仅对关键路径进行性能分析
- 避免在生产环境长时间开启
- 定期清理分析数据
- 结合指标和追踪数据进行分析

### 4. 数据管理

- 定期清理过期数据
- 监控存储空间使用
- 设置合理的数据保留策略
- 考虑数据压缩和归档

## 故障排除

### 1. 常见问题

**问题：指标数据未显示**
- 检查可观测性组件是否正确初始化
- 确认指标收集器是否正常工作
- 查看日志中的错误信息

**问题：追踪数据不完整**
- 检查追踪器是否正确集成
- 确认 Span 是否正确结束
- 查看采样率设置

**问题：性能分析数据缺失**
- 确认性能分析器是否正确启动和停止
- 检查依赖库是否安装（py-spy、memory_profiler等）
- 查看分析记录是否正确保存

### 2. 调试技巧

- 启用调试日志查看详细信息
- 使用 CLI 工具验证数据收集
- 检查存储文件是否正确写入
- 使用仪表板快速查看系统状态

## 总结

通过实现这些可观测性增强功能，clude-code 获得了：

1. **全面的性能监控**：系统、应用和业务指标的完整覆盖
2. **端到端追踪**：跨模块/服务的调用链可视化
3. **多维度性能分析**：CPU、内存、I/O 和函数级性能分析
4. **便捷的管理工具**：CLI 工具提供查询和管理功能
5. **灵活的配置选项**：可根据需求调整监控级别和存储方式

这些增强使开发者能够：
- 快速定位性能瓶颈
- 理解系统行为模式
- 优化资源使用
- 提供更好的用户体验

所有实现都遵循最佳实践，具有良好的可扩展性和维护性。