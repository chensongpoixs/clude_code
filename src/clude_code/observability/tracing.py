"""
分布式追踪系统
基于 OpenTelemetry 标准实现追踪功能
"""
from __future__ import annotations

import time
import uuid
import json
import threading
from abc import ABC, abstractmethod
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union, Callable

from clude_code.observability.logger import get_logger


class StatusCode(Enum):
    """状态码枚举"""
    OK = "OK"
    ERROR = "ERROR"
    CANCELLED = "CANCELLED"
    UNKNOWN = "UNKNOWN"


class SpanKind(Enum):
    """Span 类型枚举"""
    INTERNAL = "INTERNAL"
    SERVER = "SERVER"
    CLIENT = "CLIENT"
    PRODUCER = "PRODUCER"
    CONSUMER = "CONSUMER"


@dataclass
class SpanEvent:
    """Span 事件"""
    timestamp: float
    name: str
    attributes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SpanLink:
    """Span 链接"""
    trace_id: str
    span_id: str
    attributes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Span:
    """追踪 Span"""
    trace_id: str
    span_id: str
    parent_span_id: Optional[str] = None
    name: str = ""
    kind: SpanKind = SpanKind.INTERNAL
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    status: StatusCode = StatusCode.OK
    status_message: str = ""
    attributes: Dict[str, Any] = field(default_factory=dict)
    events: List[SpanEvent] = field(default_factory=list)
    links: List[SpanLink] = field(default_factory=list)
    
    def is_ended(self) -> bool:
        """检查 Span 是否已结束"""
        return self.end_time is not None
    
    def duration(self) -> Optional[float]:
        """获取 Span 持续时间"""
        if self.end_time is not None:
            return self.end_time - self.start_time
        return None
    
    def set_attribute(self, key: str, value: Any) -> None:
        """设置属性"""
        self.attributes[key] = value
    
    def add_event(self, name: str, attributes: Dict[str, Any] = None) -> None:
        """添加事件"""
        event = SpanEvent(
            timestamp=time.time(),
            name=name,
            attributes=attributes or {}
        )
        self.events.append(event)
    
    def set_status(self, status: StatusCode, message: str = "") -> None:
        """设置状态"""
        self.status = status
        self.status_message = message
    
    def end(self, end_time: Optional[float] = None) -> None:
        """结束 Span"""
        if self.end_time is None:
            self.end_time = end_time or time.time()


class TraceContext:
    """追踪上下文"""
    
    def __init__(self):
        self._current_span: Optional[Span] = None
        self._lock = threading.Lock()
    
    def current_span(self) -> Optional[Span]:
        """获取当前 Span"""
        with self._lock:
            return self._current_span
    
    def set_current_span(self, span: Optional[Span]) -> None:
        """设置当前 Span"""
        with self._lock:
            self._current_span = span


class Tracer:
    """追踪器"""
    
    def __init__(self, name: str):
        self.name = name
        self._spans: Dict[str, Span] = {}
        self._context = TraceContext()
        self._lock = threading.Lock()
    
    def start_span(
        self,
        name: str,
        kind: SpanKind = SpanKind.INTERNAL,
        attributes: Dict[str, Any] = None,
        links: List[SpanLink] = None
    ) -> Span:
        """开始一个新的 Span"""
        span_id = str(uuid.uuid4())
        
        # 从当前上下文获取父 Span ID 和 Trace ID
        parent_span = self._context.current_span()
        parent_span_id = parent_span.span_id if parent_span else None
        trace_id = parent_span.trace_id if parent_span else str(uuid.uuid4())
        
        span = Span(
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            name=name,
            kind=kind,
            attributes=attributes or {},
            links=links or []
        )
        
        with self._lock:
            self._spans[span_id] = span
        
        # 设置为当前 Span
        self._context.set_current_span(span)
        
        return span
    
    def end_span(self, span: Span, end_time: Optional[float] = None) -> None:
        """结束 Span"""
        span.end(end_time)
        
        # 如果这是当前 Span，清除上下文
        if self._context.current_span() == span:
            self._context.set_current_span(None)
    
    @contextmanager
    def start_as_current_span(
        self,
        name: str,
        kind: SpanKind = SpanKind.INTERNAL,
        attributes: Dict[str, Any] = None,
        links: List[SpanLink] = None
    ):
        """作为当前 Span 启动的上下文管理器"""
        span = self.start_span(name, kind, attributes, links)
        try:
            yield span
        except Exception as e:
            span.set_status(StatusCode.ERROR, str(e))
            raise
        finally:
            self.end_span(span)
    
    def get_span(self, span_id: str) -> Optional[Span]:
        """获取 Span"""
        with self._lock:
            return self._spans.get(span_id)
    
    def get_finished_spans(self) -> List[Span]:
        """获取已完成的 Span"""
        with self._lock:
            return [span for span in self._spans.values() if span.is_ended()]
    
    def get_active_spans(self) -> List[Span]:
        """获取活跃的 Span"""
        with self._lock:
            return [span for span in self._spans.values() if not span.is_ended()]
    
    def clear_spans(self) -> None:
        """清除所有 Span"""
        with self._lock:
            self._spans.clear()
        self._context.set_current_span(None)


class TraceExporter(ABC):
    """追踪导出器接口"""
    
    @abstractmethod
    def export(self, spans: List[Span]) -> None:
        """导出 Span 数据"""
        pass


class FileTraceExporter(TraceExporter):
    """文件追踪导出器"""
    
    def __init__(self, workspace_root: str):
        self.workspace_root = workspace_root
        self.logger = get_logger(__name__, workspace_root=workspace_root)
        
        # 创建存储目录
        self.storage_dir = Path(workspace_root) / ".clude" / "traces"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        # 数据文件路径
        self.data_file = self.storage_dir / "traces.jsonl"
    
    def export(self, spans: List[Span]) -> None:
        """导出 Span 数据到文件"""
        if not spans:
            return
        
        try:
            with open(self.data_file, 'a') as f:
                for span in spans:
                    data = {
                        "trace_id": span.trace_id,
                        "span_id": span.span_id,
                        "parent_span_id": span.parent_span_id,
                        "name": span.name,
                        "kind": span.kind.value,
                        "start_time": span.start_time,
                        "end_time": span.end_time,
                        "duration": span.duration(),
                        "status": span.status.value,
                        "status_message": span.status_message,
                        "attributes": span.attributes,
                        "events": [
                            {
                                "timestamp": event.timestamp,
                                "name": event.name,
                                "attributes": event.attributes
                            }
                            for event in span.events
                        ],
                        "links": [
                            {
                                "trace_id": link.trace_id,
                                "span_id": link.span_id,
                                "attributes": link.attributes
                            }
                            for link in span.links
                        ]
                    }
                    f.write(json.dumps(data) + '\n')
        except Exception as e:
            self.logger.error(f"Error exporting traces: {e}")


class ConsoleTraceExporter(TraceExporter):
    """控制台追踪导出器"""
    
    def __init__(self, workspace_root: str):
        self.workspace_root = workspace_root
        self.logger = get_logger(__name__, workspace_root=workspace_root)
    
    def export(self, spans: List[Span]) -> None:
        """导出 Span 数据到控制台"""
        if not spans:
            return
        
        for span in spans:
            duration = span.duration()
            duration_str = f"{duration * 1000:.2f}ms" if duration else "active"
            
            self.logger.info(
                f"[trace] {span.name} ({span.kind.value}) "
                f"- Duration: {duration_str} "
                f"- Status: {span.status.value} "
                f"- TraceID: {span.trace_id[:8]}... "
                f"- SpanID: {span.span_id[:8]}..."
            )
            
            if span.status_message:
                self.logger.info(f"[trace]   Message: {span.status_message}")
            
            if span.attributes:
                for key, value in span.attributes.items():
                    self.logger.info(f"[trace]   Attribute: {key}={value}")
            
            if span.events:
                for event in span.events:
                    self.logger.info(f"[trace]   Event: {event.name} at {event.timestamp}")


class SamplingTraceExporter(TraceExporter):
    """采样追踪导出器"""
    
    def __init__(self, wrapped_exporter: TraceExporter, sample_rate: float = 0.1):
        self.wrapped_exporter = wrapped_exporter
        self.sample_rate = max(0.0, min(1.0, sample_rate))  # 确保在 [0, 1] 范围内
        self.logger = get_logger(__name__)
    
    def export(self, spans: List[Span]) -> None:
        """根据采样率导出 Span 数据"""
        import random
        
        # 按 Trace ID 分组
        traces = {}
        for span in spans:
            if span.trace_id not in traces:
                traces[span.trace_id] = []
            traces[span.trace_id].append(span)
        
        # 对每个 Trace 进行采样
        sampled_spans = []
        for trace_id, trace_spans in traces.items():
            if random.random() <= self.sample_rate:
                sampled_spans.extend(trace_spans)
        
        if sampled_spans:
            self.wrapped_exporter.export(sampled_spans)
        
        self.logger.debug(f"Sampled {len(sampled_spans)}/{len(spans)} spans (rate={self.sample_rate})")


class BatchTraceExporter(TraceExporter):
    """批量追踪导出器"""
    
    def __init__(self, wrapped_exporter: TraceExporter, batch_size: int = 100, export_interval: float = 5.0):
        self.wrapped_exporter = wrapped_exporter
        self.batch_size = batch_size
        self.export_interval = export_interval
        self._spans: List[Span] = []
        self._lock = threading.Lock()
        self._timer: Optional[threading.Timer] = None
        self.logger = get_logger(__name__)
        
        # 启动定时导出
        self._schedule_export()
    
    def export(self, spans: List[Span]) -> None:
        """添加 Span 到批次"""
        with self._lock:
            self._spans.extend(spans)
            
            # 如果达到批次大小，立即导出
            if len(self._spans) >= self.batch_size:
                self._flush_spans()
    
    def _flush_spans(self) -> None:
        """刷新所有 Span 到包装的导出器"""
        with self._lock:
            if not self._spans:
                return
            
            spans_to_export = self._spans.copy()
            self._spans.clear()
        
        try:
            self.wrapped_exporter.export(spans_to_export)
            self.logger.debug(f"Exported batch of {len(spans_to_export)} spans")
        except Exception as e:
            self.logger.error(f"Error exporting batch: {e}")
    
    def _schedule_export(self) -> None:
        """安排定期导出"""
        self._timer = threading.Timer(self.export_interval, self._export_task_handler)
        self._timer.daemon = True
        self._timer.start()
    
    def _export_task_handler(self) -> None:
        """导出任务处理器"""
        try:
            self._flush_spans()
        except Exception as e:
            self.logger.error(f"Error in export task: {e}")
        finally:
            # 重新安排下一次导出
            self._schedule_export()
    
    def flush(self) -> None:
        """手动刷新所有待导出的 Span"""
        self._flush_spans()
    
    def shutdown(self) -> None:
        """关闭导出器"""
        if self._timer:
            self._timer.cancel()
            self._timer = None
        
        # 导出剩余的 Span
        self.flush()


class TraceProcessor:
    """追踪处理器"""
    
    def __init__(self, tracer: Tracer, exporter: TraceExporter):
        self.tracer = tracer
        self.exporter = exporter
        self._lock = threading.Lock()
        self._exported_span_ids: set = set()
    
    def on_span_end(self, span: Span) -> None:
        """当 Span 结束时调用"""
        with self._lock:
            # 避免重复导出
            if span.span_id in self._exported_span_ids:
                return
            
            self._exported_span_ids.add(span.span_id)
        
        # 导出已完成的 Span
        finished_spans = self.tracer.get_finished_spans()
        self.exporter.export(finished_spans)


class TraceManager:
    """追踪管理器"""
    
    def __init__(self, workspace_root: str):
        self.workspace_root = workspace_root
        self.logger = get_logger(__name__, workspace_root=workspace_root)
        
        # 创建默认追踪器
        self.tracer = Tracer("clude_code")
        
        # 创建导出器链
        file_exporter = FileTraceExporter(workspace_root)
        console_exporter = ConsoleTraceExporter(workspace_root)
        sampling_exporter = SamplingTraceExporter(file_exporter, sample_rate=0.1)
        batch_exporter = BatchTraceExporter(sampling_exporter, batch_size=50, export_interval=5.0)
        
        # 创建处理器
        self.processor = TraceProcessor(self.tracer, batch_exporter)
        
        # 启动后台线程监控 Span 结束事件
        self._monitor_thread = threading.Thread(target=self._monitor_spans, daemon=True)
        self._monitor_thread.start()
        
        # 关闭标志
        self._shutdown = False
    
    def get_tracer(self, name: Optional[str] = None) -> Tracer:
        """获取追踪器"""
        if name is None:
            return self.tracer
        return Tracer(name)
    
    def _monitor_spans(self) -> None:
        """监控 Span 结束事件"""
        while not self._shutdown:
            try:
                # 获取所有已完成的 Span
                finished_spans = self.tracer.get_finished_spans()
                
                # 导出已完成的 Span
                if finished_spans:
                    self.processor.exporter.export(finished_spans)
                
                # 清理已导出的 Span
                self.tracer.clear_spans()
                
                # 短暂休眠
                time.sleep(1.0)
            except Exception as e:
                self.logger.error(f"Error in span monitor: {e}")
    
    def shutdown(self) -> None:
        """关闭追踪管理器"""
        self._shutdown = True
        
        # 等待监控线程结束
        if self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=5.0)
        
        # 刷新导出器
        if hasattr(self.processor.exporter, 'flush'):
            self.processor.exporter.flush()
        
        if hasattr(self.processor.exporter, 'shutdown'):
            self.processor.exporter.shutdown()


# 全局追踪管理器实例
_global_manager: Optional[TraceManager] = None


def get_trace_manager(workspace_root: str = ".") -> TraceManager:
    """获取全局追踪管理器实例"""
    global _global_manager
    if _global_manager is None:
        _global_manager = TraceManager(workspace_root)
    return _global_manager


def get_tracer(name: Optional[str] = None, workspace_root: str = ".") -> Tracer:
    """获取追踪器"""
    manager = get_trace_manager(workspace_root)
    return manager.get_tracer(name)


# 便捷装饰器和函数
def trace_span(
    name: Optional[str] = None,
    kind: SpanKind = SpanKind.INTERNAL,
    tracer_name: Optional[str] = None,
    workspace_root: str = "."
):
    """追踪 Span 装饰器"""
    def decorator(func: Callable) -> Callable:
        span_name = name or f"{func.__module__}.{func.__name__}"
        
        def wrapper(*args, **kwargs):
            tracer = get_tracer(tracer_name, workspace_root)
            with tracer.start_as_current_span(span_name, kind):
                return func(*args, **kwargs)
        
        return wrapper
    return decorator


def trace_function(
    func: Callable,
    name: Optional[str] = None,
    kind: SpanKind = SpanKind.INTERNAL,
    tracer_name: Optional[str] = None,
    workspace_root: str = "."
) -> Callable:
    """追踪函数"""
    span_name = name or f"{func.__module__}.{func.__name__}"
    
    def wrapper(*args, **kwargs):
        tracer = get_tracer(tracer_name, workspace_root)
        with tracer.start_as_current_span(span_name, kind):
            return func(*args, **kwargs)
    
    return wrapper


def trace_method(
    name: Optional[str] = None,
    kind: SpanKind = SpanKind.INTERNAL,
    tracer_name: Optional[str] = None,
    workspace_root: str = "."
):
    """追踪方法装饰器"""
    def decorator(func: Callable) -> Callable:
        span_name = name or f"{func.__qualname__}"
        
        def wrapper(self, *args, **kwargs):
            tracer = get_tracer(tracer_name, workspace_root)
            with tracer.start_as_current_span(span_name, kind):
                return func(self, *args, **kwargs)
        
        return wrapper
    return decorator