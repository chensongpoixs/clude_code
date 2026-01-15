"""
性能监控指标系统
提供系统、应用和业务指标的收集、存储和查询功能
"""
from __future__ import annotations

import time
import threading
import json
import os
import psutil
from abc import ABC, abstractmethod
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union, Callable

from clude_code.observability.logger import get_logger


class MetricType(Enum):
    """指标类型枚举"""
    COUNTER = "counter"  # 计数器，只增不减
    GAUGE = "gauge"      # 仪表盘，可增可减
    HISTOGRAM = "histogram"  # 直方图，记录分布
    SUMMARY = "summary"   # 摘要，记录统计信息


@dataclass
class MetricPoint:
    """指标数据点"""
    name: str
    metric_type: MetricType
    value: Union[int, float]
    timestamp: float
    labels: Dict[str, str] = field(default_factory=dict)
    help_text: str = ""


@dataclass
class HistogramBucket:
    """直方图桶"""
    le: float  # 小于等于
    count: int


@dataclass
class SummaryStats:
    """摘要统计"""
    count: int
    sum: float
    min: float
    max: float
    avg: float
    quantiles: Dict[float, float] = field(default_factory=dict)


class Metric(ABC):
    """指标基类"""
    
    def __init__(self, name: str, help_text: str = "", labels: Dict[str, str] = None):
        self.name = name
        self.help_text = help_text
        self.labels = labels or {}
        self.created_at = time.time()
    
    @abstractmethod
    def collect(self) -> List[MetricPoint]:
        """收集指标数据点"""
        pass
    
    def with_labels(self, **labels) -> 'Metric':
        """返回带新标签的指标实例"""
        new_labels = self.labels.copy()
        new_labels.update(labels)
        return self.__class__(self.name, self.help_text, new_labels)


class Counter(Metric):
    """计数器指标"""
    
    def __init__(self, name: str, help_text: str = "", labels: Dict[str, str] = None):
        super().__init__(name, help_text, labels)
        self._value = 0
        self._lock = threading.Lock()
    
    def inc(self, amount: int = 1) -> None:
        """增加计数"""
        with self._lock:
            self._value += amount
    
    def get(self) -> int:
        """获取当前值"""
        with self._lock:
            return self._value
    
    def collect(self) -> List[MetricPoint]:
        with self._lock:
            return [MetricPoint(
                name=self.name,
                metric_type=MetricType.COUNTER,
                value=self._value,
                timestamp=time.time(),
                labels=self.labels,
                help_text=self.help_text
            )]


class Gauge(Metric):
    """仪表盘指标"""
    
    def __init__(self, name: str, help_text: str = "", labels: Dict[str, str] = None):
        super().__init__(name, help_text, labels)
        self._value = 0
        self._lock = threading.Lock()
    
    def set(self, value: Union[int, float]) -> None:
        """设置值"""
        with self._lock:
            self._value = value
    
    def inc(self, amount: Union[int, float] = 1) -> None:
        """增加值"""
        with self._lock:
            self._value += amount
    
    def dec(self, amount: Union[int, float] = 1) -> None:
        """减少值"""
        with self._lock:
            self._value -= amount
    
    def get(self) -> Union[int, float]:
        """获取当前值"""
        with self._lock:
            return self._value
    
    def collect(self) -> List[MetricPoint]:
        with self._lock:
            return [MetricPoint(
                name=self.name,
                metric_type=MetricType.GAUGE,
                value=self._value,
                timestamp=time.time(),
                labels=self.labels,
                help_text=self.help_text
            )]


class Histogram(Metric):
    """直方图指标"""
    
    def __init__(
        self, 
        name: str, 
        buckets: List[float] = None,
        help_text: str = "", 
        labels: Dict[str, str] = None
    ):
        super().__init__(name, help_text, labels)
        # 默认桶边界
        self.buckets = buckets or [0.1, 0.5, 1.0, 2.5, 5.0, 10.0]
        self._observations = []
        self._lock = threading.Lock()
    
    def observe(self, value: float) -> None:
        """记录一个观察值"""
        with self._lock:
            self._observations.append(value)
    
    def get_bucket_counts(self) -> List[HistogramBucket]:
        """获取桶计数"""
        with self._lock:
            if not self._observations:
                return [HistogramBucket(le=le, count=0) for le in self.buckets] + [
                    HistogramBucket(le=float('inf'), count=0)
                ]
            
            sorted_obs = sorted(self._observations)
            total = len(sorted_obs)
            
            buckets = []
            for le in self.buckets:
                # 计算小于等于 le 的观察值数量
                count = sum(1 for v in sorted_obs if v <= le)
                buckets.append(HistogramBucket(le=le, count=count))
            
            # 添加最后一个桶（+inf）
            buckets.append(HistogramBucket(le=float('inf'), count=total))
            
            return buckets
    
    def collect(self) -> List[MetricPoint]:
        with self._lock:
            points = []
            
            # 添加桶计数
            for bucket in self.get_bucket_counts():
                bucket_name = f"{self.name}_bucket"
                bucket_labels = self.labels.copy()
                bucket_labels["le"] = str(bucket.le)
                points.append(MetricPoint(
                    name=bucket_name,
                    metric_type=MetricType.COUNTER,
                    value=bucket.count,
                    timestamp=time.time(),
                    labels=bucket_labels,
                    help_text=f"{self.help_text} (bucket le={bucket.le})"
                ))
            
            # 添加观察值总数
            points.append(MetricPoint(
                name=f"{self.name}_count",
                metric_type=MetricType.COUNTER,
                value=len(self._observations),
                timestamp=time.time(),
                labels=self.labels,
                help_text=f"{self.help_text} (total count)"
            ))
            
            # 添加观察值总和
            points.append(MetricPoint(
                name=f"{self.name}_sum",
                metric_type=MetricType.COUNTER,
                value=sum(self._observations),
                timestamp=time.time(),
                labels=self.labels,
                help_text=f"{self.help_text} (sum)"
            ))
            
            return points


class Summary(Metric):
    """摘要指标"""
    
    def __init__(
        self, 
        name: str, 
        quantiles: List[float] = None,
        help_text: str = "", 
        labels: Dict[str, str] = None,
        max_age: float = 600,  # 10分钟
        age_buckets: int = 5  # 5个时间桶
    ):
        super().__init__(name, help_text, labels)
        self.quantiles = quantiles or [0.5, 0.9, 0.95, 0.99]
        self.max_age = max_age
        self.age_buckets = age_buckets
        self._time_buckets = deque(maxlen=age_buckets)
        self._lock = threading.Lock()
    
    def observe(self, value: float) -> None:
        """记录一个观察值"""
        with self._lock:
            now = time.time()
            # 创建或获取当前时间桶
            if not self._time_buckets or now - self._time_buckets[-1]["timestamp"] > self.max_age / self.age_buckets:
                self._time_buckets.append({"timestamp": now, "values": []})
            
            # 添加值到当前桶
            self._time_buckets[-1]["values"].append(value)
    
    def get_stats(self) -> SummaryStats:
        """获取统计信息"""
        with self._lock:
            # 收集所有有效时间桶的值
            now = time.time()
            all_values = []
            
            for bucket in self._time_buckets:
                if now - bucket["timestamp"] <= self.max_age:
                    all_values.extend(bucket["values"])
            
            if not all_values:
                return SummaryStats(
                    count=0,
                    sum=0.0,
                    min=0.0,
                    max=0.0,
                    avg=0.0,
                    quantiles={}
                )
            
            # 计算统计信息
            count = len(all_values)
            total = sum(all_values)
            minimum = min(all_values)
            maximum = max(all_values)
            average = total / count
            
            # 计算分位数
            sorted_values = sorted(all_values)
            quantiles = {}
            for q in self.quantiles:
                index = int(q * len(sorted_values))
                if index >= len(sorted_values):
                    index = len(sorted_values) - 1
                quantiles[q] = sorted_values[index]
            
            return SummaryStats(
                count=count,
                sum=total,
                min=minimum,
                max=maximum,
                avg=average,
                quantiles=quantiles
            )
    
    def collect(self) -> List[MetricPoint]:
        with self._lock:
            stats = self.get_stats()
            points = []
            
            # 添加计数
            points.append(MetricPoint(
                name=f"{self.name}_count",
                metric_type=MetricType.GAUGE,
                value=stats.count,
                timestamp=time.time(),
                labels=self.labels,
                help_text=f"{self.help_text} (count)"
            ))
            
            # 添加总和
            points.append(MetricPoint(
                name=f"{self.name}_sum",
                metric_type=MetricType.GAUGE,
                value=stats.sum,
                timestamp=time.time(),
                labels=self.labels,
                help_text=f"{self.help_text} (sum)"
            ))
            
            # 添加基本统计
            for stat_name, value in [
                ("min", stats.min), ("max", stats.max), ("avg", stats.avg)
            ]:
                points.append(MetricPoint(
                    name=f"{self.name}_{stat_name}",
                    metric_type=MetricType.GAUGE,
                    value=value,
                    timestamp=time.time(),
                    labels=self.labels,
                    help_text=f"{self.help_text} ({stat_name})"
                ))
            
            # 添加分位数
            for quantile, value in stats.quantiles.items():
                points.append(MetricPoint(
                    name=f"{self.name}",
                    metric_type=MetricType.GAUGE,
                    value=value,
                    timestamp=time.time(),
                    labels={**self.labels, "quantile": str(quantile)},
                    help_text=f"{self.help_text} (quantile {quantile})"
                ))
            
            return points


class MetricsCollector:
    """指标收集器"""
    
    def __init__(self, workspace_root: str):
        self.workspace_root = workspace_root
        self.logger = get_logger(__name__, workspace_root=workspace_root)
        self._metrics: Dict[str, Metric] = {}
        self._collectors: List[Callable[[], List[MetricPoint]]] = []
        self._lock = threading.Lock()
    
    def register_metric(self, metric: Metric) -> Metric:
        """注册指标"""
        with self._lock:
            self._metrics[metric.name] = metric
            self.logger.debug(f"Registered metric: {metric.name}")
        return metric
    
    def get_metric(self, name: str) -> Optional[Metric]:
        """获取指标"""
        with self._lock:
            return self._metrics.get(name)
    
    def register_collector(self, collector: Callable[[], List[MetricPoint]]) -> None:
        """注册收集器函数"""
        with self._lock:
            self._collectors.append(collector)
    
    def collect_all(self) -> List[MetricPoint]:
        """收集所有指标数据点"""
        points = []
        
        with self._lock:
            # 收集注册的指标
            for metric in self._metrics.values():
                try:
                    points.extend(metric.collect())
                except Exception as e:
                    self.logger.error(f"Error collecting metric {metric.name}: {e}")
            
            # 收集收集器函数的数据
            for collector in self._collectors:
                try:
                    points.extend(collector())
                except Exception as e:
                    self.logger.error(f"Error in collector: {e}")
        
        return points
    
    def counter(self, name: str, help_text: str = "", labels: Dict[str, str] = None) -> Counter:
        """创建或获取计数器指标"""
        metric = self.get_metric(name)
        if metric is None:
            metric = Counter(name, help_text, labels)
            self.register_metric(metric)
        elif not isinstance(metric, Counter):
            raise ValueError(f"Metric {name} already exists with different type")
        return metric
    
    def gauge(self, name: str, help_text: str = "", labels: Dict[str, str] = None) -> Gauge:
        """创建或获取仪表盘指标"""
        metric = self.get_metric(name)
        if metric is None:
            metric = Gauge(name, help_text, labels)
            self.register_metric(metric)
        elif not isinstance(metric, Gauge):
            raise ValueError(f"Metric {name} already exists with different type")
        return metric
    
    def histogram(self, name: str, buckets: List[float] = None, help_text: str = "", labels: Dict[str, str] = None) -> Histogram:
        """创建或获取直方图指标"""
        metric = self.get_metric(name)
        if metric is None:
            metric = Histogram(name, buckets, help_text, labels)
            self.register_metric(metric)
        elif not isinstance(metric, Histogram):
            raise ValueError(f"Metric {name} already exists with different type")
        return metric
    
    def summary(self, name: str, quantiles: List[float] = None, help_text: str = "", labels: Dict[str, str] = None) -> Summary:
        """创建或获取摘要指标"""
        metric = self.get_metric(name)
        if metric is None:
            metric = Summary(name, quantiles, help_text, labels)
            self.register_metric(metric)
        elif not isinstance(metric, Summary):
            raise ValueError(f"Metric {name} already exists with different type")
        return metric


# 全局指标收集器实例
_global_collector: Optional[MetricsCollector] = None


def get_metrics_collector(workspace_root: str = ".") -> MetricsCollector:
    """获取全局指标收集器实例"""
    global _global_collector
    if _global_collector is None:
        _global_collector = MetricsCollector(workspace_root)
        # 注册系统指标收集器
        _global_collector.register_collector(lambda: collect_system_metrics(workspace_root))
    return _global_collector


def collect_system_metrics(workspace_root: str) -> List[MetricPoint]:
    """收集系统指标"""
    points = []
    timestamp = time.time()
    
    try:
        # CPU 指标
        cpu_percent = psutil.cpu_percent(interval=0.1)
        points.append(MetricPoint(
            name="system_cpu_percent",
            metric_type=MetricType.GAUGE,
            value=cpu_percent,
            timestamp=timestamp,
            help_text="CPU 使用率 (%)"
        ))
        
        # 内存指标
        memory = psutil.virtual_memory()
        points.append(MetricPoint(
            name="system_memory_percent",
            metric_type=MetricType.GAUGE,
            value=memory.percent,
            timestamp=timestamp,
            help_text="内存使用率 (%)"
        ))
        
        points.append(MetricPoint(
            name="system_memory_bytes",
            metric_type=MetricType.GAUGE,
            value=memory.used,
            timestamp=timestamp,
            labels={"type": "used"},
            help_text="已使用内存 (字节)"
        ))
        
        points.append(MetricPoint(
            name="system_memory_bytes",
            metric_type=MetricType.GAUGE,
            value=memory.total,
            timestamp=timestamp,
            labels={"type": "total"},
            help_text="总内存 (字节)"
        ))
        
        # 磁盘指标
        disk = psutil.disk_usage(workspace_root)
        points.append(MetricPoint(
            name="system_disk_percent",
            metric_type=MetricType.GAUGE,
            value=disk.percent,
            timestamp=timestamp,
            help_text="磁盘使用率 (%)"
        ))
        
        points.append(MetricPoint(
            name="system_disk_bytes",
            metric_type=MetricType.GAUGE,
            value=disk.used,
            timestamp=timestamp,
            labels={"type": "used"},
            help_text="已使用磁盘空间 (字节)"
        ))
        
        points.append(MetricPoint(
            name="system_disk_bytes",
            metric_type=MetricType.GAUGE,
            value=disk.total,
            timestamp=timestamp,
            labels={"type": "total"},
            help_text="总磁盘空间 (字节)"
        ))
        
        # 网络指标
        network = psutil.net_io_counters()
        if network:
            points.append(MetricPoint(
                name="system_network_bytes",
                metric_type=MetricType.COUNTER,
                value=network.bytes_sent,
                timestamp=timestamp,
                labels={"direction": "sent"},
                help_text="发送网络字节数"
            ))
            
            points.append(MetricPoint(
                name="system_network_bytes",
                metric_type=MetricType.COUNTER,
                value=network.bytes_recv,
                timestamp=timestamp,
                labels={"direction": "recv"},
                help_text="接收网络字节数"
            ))
    
    except Exception as e:
        # 记录错误但不中断程序
        logger = get_logger(__name__, workspace_root=workspace_root)
        logger.error(f"Error collecting system metrics: {e}")
    
    return points