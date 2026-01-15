"""
可观测性组件集成
整合指标收集、追踪和性能分析功能
"""
from __future__ import annotations

import time
import threading
from typing import Any, Dict, List, Optional, Union

from clude_code.config import CludeConfig
from clude_code.observability.logger import get_logger
from clude_code.observability.metrics import get_metrics_collector, MetricType
from clude_code.observability.metrics_storage import get_metrics_manager, StorageBackend, MetricsQuery
from clude_code.observability.tracing import get_tracer, SpanKind, trace_span, trace_method
from clude_code.observability.profiler import get_profile_manager, ProfileType, profile


class ObservabilityManager:
    """可观测性管理器"""
    
    def __init__(self, cfg: CludeConfig):
        self.cfg = cfg
        self.workspace_root = cfg.workspace_root
        self.logger = get_logger(__name__, workspace_root=cfg.workspace_root)
        
        # 初始化各个组件
        self.metrics_collector = get_metrics_collector(cfg.workspace_root)
        self.metrics_manager = get_metrics_manager(
            workspace_root=cfg.workspace_root,
            storage_backend=StorageBackend.FILE,
            storage_options={"max_file_size_mb": 50}
        )
        self.tracer = get_tracer("clude_code", cfg.workspace_root)
        self.profile_manager = get_profile_manager(cfg.workspace_root)
        
        # 创建业务指标
        self._setup_business_metrics()
        
        # 启动后台任务
        self._background_tasks: List[threading.Thread] = []
        self._shutdown = False
        
        # 启动指标收集任务
        self._start_metrics_collection()
    
    def _setup_business_metrics(self) -> None:
        """设置业务指标"""
        # LLM 相关指标
        self.llm_request_counter = self.metrics_collector.counter(
            "llm_requests_total",
            "Total number of LLM requests"
        )
        self.llm_request_duration = self.metrics_collector.histogram(
            "llm_request_duration_seconds",
            buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
            help_text="LLM request duration in seconds"
        )
        self.llm_tokens_used = self.metrics_collector.counter(
            "llm_tokens_used_total",
            "Total number of LLM tokens used"
        )
        self.llm_cache_hits = self.metrics_collector.counter(
            "llm_cache_hits_total",
            "Total number of LLM cache hits"
        )
        self.llm_cache_misses = self.metrics_collector.counter(
            "llm_cache_misses_total",
            "Total number of LLM cache misses"
        )
        
        # 工具调用指标
        self.tool_call_counter = self.metrics_collector.counter(
            "tool_calls_total",
            "Total number of tool calls",
            labels={"tool": "unknown"}
        )
        self.tool_call_duration = self.metrics_collector.histogram(
            "tool_call_duration_seconds",
            buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0],
            help_text="Tool call duration in seconds"
        )
        self.tool_call_errors = self.metrics_collector.counter(
            "tool_call_errors_total",
            "Total number of tool call errors",
            labels={"tool": "unknown"}
        )
        
        # 文件操作指标
        self.file_operation_counter = self.metrics_collector.counter(
            "file_operations_total",
            "Total number of file operations",
            labels={"operation": "unknown", "file_type": "unknown"}
        )
        self.file_operation_bytes = self.metrics_collector.histogram(
            "file_operation_bytes",
            buckets=[1024, 4096, 16384, 65536, 262144, 1048576],
            help_text="File operation size in bytes"
        )
        
        # 任务执行指标
        self.task_execution_counter = self.metrics_collector.counter(
            "task_executions_total",
            "Total number of task executions",
            labels={"task_type": "unknown", "status": "unknown"}
        )
        self.task_execution_duration = self.metrics_collector.histogram(
            "task_execution_duration_seconds",
            buckets=[1.0, 5.0, 10.0, 30.0, 60.0, 300.0],
            help_text="Task execution duration in seconds"
        )
        
        # 会话指标
        self.active_sessions = self.metrics_collector.gauge(
            "active_sessions",
            "Number of active sessions"
        )
        self.session_counter = self.metrics_collector.counter(
            "sessions_total",
            "Total number of sessions"
        )
    
    def _start_metrics_collection(self) -> None:
        """启动指标收集任务"""
        def collect_metrics():
            while not self._shutdown:
                try:
                    # 收集所有指标
                    points = self.metrics_collector.collect_all()
                    
                    # 存储到指标管理器
                    self.metrics_manager.store(points)
                    
                    # 短暂休眠
                    time.sleep(10)  # 每10秒收集一次
                except Exception as e:
                    self.logger.error(f"Error in metrics collection: {e}")
                    time.sleep(10)
        
        thread = threading.Thread(target=collect_metrics, daemon=True)
        thread.start()
        self._background_tasks.append(thread)
    
    def record_llm_request(
        self,
        duration: float,
        tokens_used: int = 0,
        cache_hit: bool = False
    ) -> None:
        """记录 LLM 请求"""
        self.llm_request_counter.inc()
        self.llm_request_duration.observe(duration)
        self.llm_tokens_used.inc(tokens_used)
        
        if cache_hit:
            self.llm_cache_hits.inc()
        else:
            self.llm_cache_misses.inc()
        
        # 记录追踪
        with self.tracer.start_as_current_span("llm_request", SpanKind.CLIENT) as span:
            span.set_attribute("duration", duration)
            span.set_attribute("tokens_used", tokens_used)
            span.set_attribute("cache_hit", cache_hit)
    
    def record_tool_call(
        self,
        tool_name: str,
        duration: float,
        success: bool = True,
        file_size: int = 0
    ) -> None:
        """记录工具调用"""
        # 记录指标
        self.tool_call_counter.with_labels(tool=tool_name).inc()
        self.tool_call_duration.observe(duration)
        
        if not success:
            self.tool_call_errors.with_labels(tool=tool_name).inc()
        
        # 记录文件操作
        if tool_name in ["read_file", "write_file", "apply_patch", "undo_patch"]:
            operation = "read" if tool_name == "read_file" else "write"
            file_type = "unknown"
            if tool_name in ["read_file", "write_file"]:
                file_type = "regular"
            elif tool_name in ["apply_patch", "undo_patch"]:
                file_type = "patch"
            
            self.file_operation_counter.with_labels(operation=operation, file_type=file_type).inc()
            if file_size > 0:
                self.file_operation_bytes.observe(file_size)
        
        # 记录追踪
        with self.tracer.start_as_current_span(f"tool_call:{tool_name}", SpanKind.INTERNAL) as span:
            span.set_attribute("tool_name", tool_name)
            span.set_attribute("duration", duration)
            span.set_attribute("success", success)
            span.set_attribute("file_size", file_size)
            
            if not success:
                span.set_status("ERROR", "Tool call failed")
    
    def record_task_execution(
        self,
        task_type: str,
        duration: float,
        success: bool = True,
        error_message: str = ""
    ) -> None:
        """记录任务执行"""
        status = "success" if success else "error"
        
        # 记录指标
        self.task_execution_counter.with_labels(task_type=task_type, status=status).inc()
        self.task_execution_duration.observe(duration)
        
        # 记录追踪
        with self.tracer.start_as_current_span(f"task:{task_type}", SpanKind.INTERNAL) as span:
            span.set_attribute("task_type", task_type)
            span.set_attribute("duration", duration)
            span.set_attribute("success", success)
            
            if not success and error_message:
                span.set_attribute("error_message", error_message)
                span.set_status("ERROR", error_message)
    
    def start_session(self, session_id: str) -> None:
        """开始会话"""
        self.active_sessions.inc()
        self.session_counter.inc()
        
        # 记录追踪
        with self.tracer.start_as_current_span("session", SpanKind.INTERNAL) as span:
            span.set_attribute("session_id", session_id)
            span.set_attribute("event", "start")
    
    def end_session(self, session_id: str) -> None:
        """结束会话"""
        self.active_sessions.dec()
        
        # 记录追踪
        with self.tracer.start_as_current_span("session", SpanKind.INTERNAL) as span:
            span.set_attribute("session_id", session_id)
            span.set_attribute("event", "end")
    
    def start_profiling(self, name: str, profile_type: ProfileType = ProfileType.FUNCTION) -> bool:
        """开始性能分析"""
        return self.profile_manager.start_profiling(name, profile_type)
    
    def stop_profiling(self, profile_type: ProfileType = ProfileType.FUNCTION) -> Optional[Any]:
        """停止性能分析"""
        return self.profile_manager.stop_profiling(profile_type)
    
    def get_metrics_summary(self, hours: int = 1) -> Dict[str, Any]:
        """获取指标摘要"""
        end_time = time.time()
        start_time = end_time - hours * 3600
        
        summary = {}
        
        # LLM 指标
        llm_requests = self.metrics_manager.query(MetricsQuery(
            name="llm_requests_total",
            start_time=start_time,
            end_time=end_time
        ))
        summary["llm_requests"] = sum(p.value for p in llm_requests)
        
        llm_durations = self.metrics_manager.query(MetricsQuery(
            name="llm_request_duration_seconds",
            start_time=start_time,
            end_time=end_time
        ))
        if llm_durations:
            durations = [p.value for p in llm_durations]
            summary["llm_avg_duration"] = sum(durations) / len(durations)
            summary["llm_max_duration"] = max(durations)
        else:
            summary["llm_avg_duration"] = 0
            summary["llm_max_duration"] = 0
        
        # 工具调用指标
        tool_calls = self.metrics_manager.query(MetricsQuery(
            name="tool_calls_total",
            start_time=start_time,
            end_time=end_time
        ))
        summary["tool_calls"] = sum(p.value for p in tool_calls)
        
        tool_errors = self.metrics_manager.query(MetricsQuery(
            name="tool_call_errors_total",
            start_time=start_time,
            end_time=end_time
        ))
        summary["tool_errors"] = sum(p.value for p in tool_errors)
        
        # 任务执行指标
        task_executions = self.metrics_manager.query(MetricsQuery(
            name="task_executions_total",
            start_time=start_time,
            end_time=end_time
        ))
        summary["task_executions"] = sum(p.value for p in task_executions)
        
        return summary
    
    def get_trace_summary(self, hours: int = 1) -> Dict[str, Any]:
        """获取追踪摘要"""
        # 这里可以实现更复杂的追踪分析
        # 目前返回基本信息
        return {
            "trace_count": "See trace files for details",
            "trace_location": str(self.workspace_root / ".clude" / "traces" / "traces.jsonl")
        }
    
    def get_profile_summary(self, profile_type: Optional[ProfileType] = None) -> Dict[str, Any]:
        """获取性能分析摘要"""
        records = self.profile_manager.get_records(profile_type, limit=10)
        
        summary = {
            "profile_count": len(records),
            "profiles": []
        }
        
        for record in records:
            summary["profiles"].append({
                "name": record.name,
                "type": record.profile_type.value,
                "duration": record.duration,
                "timestamp": record.start_time
            })
        
        return summary
    
    def export_metrics(self, format: str = "prometheus", hours: int = 1) -> str:
        """导出指标数据"""
        end_time = time.time()
        start_time = end_time - hours * 3600
        
        query = MetricsQuery(start_time=start_time, end_time=end_time)
        return self.metrics_manager.export(format, query)
    
    def shutdown(self) -> None:
        """关闭可观测性管理器"""
        self._shutdown = True
        
        # 等待后台任务结束
        for thread in self._background_tasks:
            if thread.is_alive():
                thread.join(timeout=5.0)
        
        # 保存性能分析记录
        self.profile_manager.save_records()
        
        self.logger.info("Observability manager shutdown")


# 全局可观测性管理器实例
_global_manager: Optional[ObservabilityManager] = None


def get_observability_manager(cfg: CludeConfig) -> ObservabilityManager:
    """获取全局可观测性管理器实例"""
    global _global_manager
    if _global_manager is None:
        _global_manager = ObservabilityManager(cfg)
    return _global_manager


# 便捷装饰器
def observe_llm_request(func):
    """LLM 请求观察装饰器"""
    def wrapper(self, *args, **kwargs):
        start_time = time.time()
        try:
            result = func(self, *args, **kwargs)
            
            # 尝试从结果中提取 token 数量
            tokens_used = 0
            if hasattr(result, 'usage') and hasattr(result.usage, 'total_tokens'):
                tokens_used = result.usage.total_tokens
            
            # 记录指标
            manager = get_observability_manager(self.cfg)
            manager.record_llm_request(
                duration=time.time() - start_time,
                tokens_used=tokens_used,
                cache_hit=getattr(result, 'cache_hit', False)
            )
            
            return result
        except Exception as e:
            # 记录失败的请求
            manager = get_observability_manager(self.cfg)
            manager.record_llm_request(
                duration=time.time() - start_time,
                cache_hit=False
            )
            raise
    
    return wrapper


def observe_tool_call(tool_name: str):
    """工具调用观察装饰器"""
    def decorator(func):
        def wrapper(self, *args, **kwargs):
            start_time = time.time()
            file_size = 0
            
            try:
                # 尝试从参数中提取文件大小
                if 'path' in kwargs:
                    try:
                        file_size = Path(kwargs['path']).stat().st_size
                    except:
                        pass
                
                result = func(self, *args, **kwargs)
                
                # 记录成功的工具调用
                manager = get_observability_manager(self.cfg)
                manager.record_tool_call(
                    tool_name=tool_name,
                    duration=time.time() - start_time,
                    success=True,
                    file_size=file_size
                )
                
                return result
            except Exception as e:
                # 记录失败的工具调用
                manager = get_observability_manager(self.cfg)
                manager.record_tool_call(
                    tool_name=tool_name,
                    duration=time.time() - start_time,
                    success=False,
                    file_size=file_size
                )
                raise
        
        return wrapper
    return decorator


def observe_task_execution(task_type: str):
    """任务执行观察装饰器"""
    def decorator(func):
        def wrapper(self, *args, **kwargs):
            start_time = time.time()
            
            try:
                result = func(self, *args, **kwargs)
                
                # 记录成功的任务执行
                manager = get_observability_manager(self.cfg)
                manager.record_task_execution(
                    task_type=task_type,
                    duration=time.time() - start_time,
                    success=True
                )
                
                return result
            except Exception as e:
                # 记录失败的任务执行
                manager = get_observability_manager(self.cfg)
                manager.record_task_execution(
                    task_type=task_type,
                    duration=time.time() - start_time,
                    success=False,
                    error_message=str(e)
                )
                raise
        
        return wrapper
    return decorator