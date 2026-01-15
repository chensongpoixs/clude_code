"""
指标存储和导出组件
支持多种存储后端和导出格式
"""
from __future__ import annotations

import json
import time
import threading
from abc import ABC, abstractmethod
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from clude_code.observability.metrics import MetricPoint, MetricType
from clude_code.observability.logger import get_logger


class StorageBackend(Enum):
    """存储后端类型"""
    MEMORY = "memory"
    FILE = "file"
    REMOTE = "remote"  # 预留，未来实现


@dataclass
class MetricsQuery:
    """指标查询"""
    name: Optional[str] = None
    metric_type: Optional[MetricType] = None
    labels: Dict[str, str] = field(default_factory=dict)
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    limit: Optional[int] = None


class MetricsStorage(ABC):
    """指标存储接口"""
    
    @abstractmethod
    def store(self, points: List[MetricPoint]) -> None:
        """存储指标数据点"""
        pass
    
    @abstractmethod
    def query(self, query: MetricsQuery) -> List[MetricPoint]:
        """查询指标数据点"""
        pass
    
    @abstractmethod
    def get_metric_names(self) -> List[str]:
        """获取所有指标名称"""
        pass
    
    @abstractmethod
    def cleanup(self, retention_hours: int = 24) -> int:
        """清理过期数据，返回删除的数据点数量"""
        pass


class MemoryMetricsStorage(MetricsStorage):
    """内存指标存储"""
    
    def __init__(self, max_points: int = 10000):
        self.max_points = max_points
        self._points: deque = deque(maxlen=max_points)
        self._index: Dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()
    
    def store(self, points: List[MetricPoint]) -> None:
        """存储指标数据点"""
        with self._lock:
            for point in points:
                self._points.append(point)
                self._index[point.name].append(point)
    
    def query(self, query: MetricsQuery) -> List[MetricPoint]:
        """查询指标数据点"""
        with self._lock:
            # 确定数据源
            if query.name:
                source_points = list(self._index.get(query.name, []))
            else:
                source_points = list(self._points)
            
            # 应用过滤条件
            filtered_points = []
            for point in source_points:
                # 指标类型过滤
                if query.metric_type and point.metric_type != query.metric_type:
                    continue
                
                # 标签过滤
                if query.labels:
                    if not all(point.labels.get(k) == v for k, v in query.labels.items()):
                        continue
                
                # 时间范围过滤
                if query.start_time and point.timestamp < query.start_time:
                    continue
                
                if query.end_time and point.timestamp > query.end_time:
                    continue
                
                filtered_points.append(point)
            
            # 排序和限制
            filtered_points.sort(key=lambda p: p.timestamp, reverse=True)
            
            if query.limit:
                filtered_points = filtered_points[:query.limit]
            
            return filtered_points
    
    def get_metric_names(self) -> List[str]:
        """获取所有指标名称"""
        with self._lock:
            return list(self._index.keys())
    
    def cleanup(self, retention_hours: int = 24) -> int:
        """清理过期数据"""
        cutoff_time = time.time() - retention_hours * 3600
        removed_count = 0
        
        with self._lock:
            # 重建索引，只保留有效数据
            new_points = deque(maxlen=self.max_points)
            new_index = defaultdict(deque)
            
            for point in self._points:
                if point.timestamp >= cutoff_time:
                    new_points.append(point)
                    new_index[point.name].append(point)
                else:
                    removed_count += 1
            
            self._points = new_points
            self._index = new_index
        
        return removed_count
    
    def clear(self) -> None:
        """清空所有数据"""
        with self._lock:
            self._points.clear()
            self._index.clear()


class FileMetricsStorage(MetricsStorage):
    """文件指标存储"""
    
    def __init__(self, workspace_root: str, max_file_size_mb: int = 100):
        self.workspace_root = workspace_root
        self.max_file_size = max_file_size_mb * 1024 * 1024  # 转换为字节
        self.logger = get_logger(__name__, workspace_root=workspace_root)
        
        # 创建存储目录
        self.storage_dir = Path(workspace_root) / ".clude" / "metrics"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        # 数据文件路径
        self.data_file = self.storage_dir / "data.jsonl"
        self.index_file = self.storage_dir / "index.json"
        
        # 内存缓存
        self._index_cache: Optional[Dict[str, Any]] = None
        self._cache_lock = threading.Lock()
        
        # 初始化
        self._ensure_files()
    
    def _ensure_files(self) -> None:
        """确保文件存在"""
        if not self.data_file.exists():
            self.data_file.touch()
        
        if not self.index_file.exists():
            with open(self.index_file, 'w') as f:
                json.dump({"metrics": {}, "updated": time.time()}, f)
    
    def _load_index(self) -> Dict[str, Any]:
        """加载索引"""
        with self._cache_lock:
            if self._index_cache is None:
                try:
                    with open(self.index_file, 'r') as f:
                        self._index_cache = json.load(f)
                except (json.JSONDecodeError, FileNotFoundError):
                    self._index_cache = {"metrics": {}, "updated": time.time()}
        
            return self._index_cache
    
    def _save_index(self, index: Dict[str, Any]) -> None:
        """保存索引"""
        with self._cache_lock:
            self._index_cache = index
            try:
                with open(self.index_file, 'w') as f:
                    json.dump(index, f)
            except Exception as e:
                self.logger.error(f"Error saving metrics index: {e}")
    
    def store(self, points: List[MetricPoint]) -> None:
        """存储指标数据点"""
        if not points:
            return
        
        # 检查文件大小
        if self.data_file.stat().st_size > self.max_file_size:
            self.logger.warning(f"Metrics file size exceeds limit, consider cleanup")
        
        # 追加到数据文件
        with open(self.data_file, 'a') as f:
            for point in points:
                data = {
                    "name": point.name,
                    "metric_type": point.metric_type.value,
                    "value": point.value,
                    "timestamp": point.timestamp,
                    "labels": point.labels,
                    "help_text": point.help_text
                }
                f.write(json.dumps(data) + '\n')
        
        # 更新索引
        index = self._load_index()
        for point in points:
            if point.name not in index["metrics"]:
                index["metrics"][point.name] = {
                    "metric_type": point.metric_type.value,
                    "labels": point.labels,
                    "help_text": point.help_text,
                    "first_seen": point.timestamp,
                    "last_seen": point.timestamp,
                    "count": 1
                }
            else:
                metric_info = index["metrics"][point.name]
                metric_info["last_seen"] = point.timestamp
                metric_info["count"] += 1
        
        index["updated"] = time.time()
        self._save_index(index)
    
    def query(self, query: MetricsQuery) -> List[MetricPoint]:
        """查询指标数据点"""
        # 对于文件存储，我们使用简单的线性扫描
        # 在实际生产环境中，可以考虑使用时序数据库
        points = []
        
        try:
            with open(self.data_file, 'r') as f:
                for line in f:
                    try:
                        data = json.loads(line.strip())
                        point = MetricPoint(
                            name=data["name"],
                            metric_type=MetricType(data["metric_type"]),
                            value=data["value"],
                            timestamp=data["timestamp"],
                            labels=data["labels"],
                            help_text=data.get("help_text", "")
                        )
                        
                        # 应用过滤条件
                        if query.name and point.name != query.name:
                            continue
                        
                        if query.metric_type and point.metric_type != query.metric_type:
                            continue
                        
                        if query.labels:
                            if not all(point.labels.get(k) == v for k, v in query.labels.items()):
                                continue
                        
                        if query.start_time and point.timestamp < query.start_time:
                            continue
                        
                        if query.end_time and point.timestamp > query.end_time:
                            continue
                        
                        points.append(point)
                    except (json.JSONDecodeError, KeyError, ValueError):
                        continue
        except FileNotFoundError:
            return []
        
        # 排序和限制
        points.sort(key=lambda p: p.timestamp, reverse=True)
        
        if query.limit:
            points = points[:query.limit]
        
        return points
    
    def get_metric_names(self) -> List[str]:
        """获取所有指标名称"""
        index = self._load_index()
        return list(index["metrics"].keys())
    
    def cleanup(self, retention_hours: int = 24) -> int:
        """清理过期数据"""
        cutoff_time = time.time() - retention_hours * 3600
        removed_count = 0
        
        # 创建临时文件
        temp_file = self.data_file.with_suffix('.tmp')
        
        try:
            with open(self.data_file, 'r') as infile, open(temp_file, 'w') as outfile:
                for line in infile:
                    try:
                        data = json.loads(line.strip())
                        if data["timestamp"] >= cutoff_time:
                            outfile.write(line)
                        else:
                            removed_count += 1
                    except (json.JSONDecodeError, KeyError):
                        outfile.write(line)  # 保留无法解析的行
            
            # 替换原文件
            temp_file.replace(self.data_file)
            
            # 更新索引
            index = self._load_index()
            for name, metric_info in list(index["metrics"].items()):
                if metric_info["last_seen"] < cutoff_time:
                    del index["metrics"][name]
            
            index["updated"] = time.time()
            self._save_index(index)
            
            self.logger.info(f"Cleaned up {removed_count} expired metric points")
            return removed_count
        
        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")
            # 清理临时文件
            if temp_file.exists():
                temp_file.unlink()
            return 0


class MetricsExporter(ABC):
    """指标导出器接口"""
    
    @abstractmethod
    def export(self, points: List[MetricPoint]) -> str:
        """导出指标数据为字符串"""
        pass


class PrometheusExporter(MetricsExporter):
    """Prometheus 格式导出器"""
    
    def export(self, points: List[MetricPoint]) -> str:
        """导出为 Prometheus 格式"""
        lines = []
        
        # 按指标名称分组
        grouped = defaultdict(list)
        for point in points:
            grouped[point.name].append(point)
        
        # 生成 Prometheus 格式
        for name, metric_points in grouped.items():
            if not metric_points:
                continue
            
            # 添加 HELP 和 TYPE
            if metric_points[0].help_text:
                lines.append(f"# HELP {name} {metric_points[0].help_text}")
            
            lines.append(f"# TYPE {name} {metric_points[0].metric_type.value}")
            
            # 添加数据点
            for point in metric_points:
                # 处理标签
                label_str = ""
                if point.labels:
                    label_pairs = [f'{k}="{v}"' for k, v in point.labels.items()]
                    label_str = "{" + ",".join(label_pairs) + "}"
                
                lines.append(f"{name}{label_str} {point.value} {int(point.timestamp * 1000)}")
            
            lines.append("")  # 空行分隔不同指标
        
        return "\n".join(lines)


class JsonExporter(MetricsExporter):
    """JSON 格式导出器"""
    
    def export(self, points: List[MetricPoint]) -> str:
        """导出为 JSON 格式"""
        data = []
        for point in points:
            data.append({
                "name": point.name,
                "metric_type": point.metric_type.value,
                "value": point.value,
                "timestamp": point.timestamp,
                "labels": point.labels,
                "help_text": point.help_text
            })
        
        return json.dumps(data, indent=2)


class MetricsManager:
    """指标管理器，整合存储和导出功能"""
    
    def __init__(
        self, 
        workspace_root: str,
        storage_backend: StorageBackend = StorageBackend.FILE,
        storage_options: Dict[str, Any] = None
    ):
        self.workspace_root = workspace_root
        self.logger = get_logger(__name__, workspace_root=workspace_root)
        
        # 初始化存储后端
        storage_options = storage_options or {}
        if storage_backend == StorageBackend.MEMORY:
            self.storage = MemoryMetricsStorage(**storage_options)
        elif storage_backend == StorageBackend.FILE:
            self.storage = FileMetricsStorage(workspace_root, **storage_options)
        else:
            raise ValueError(f"Unsupported storage backend: {storage_backend}")
        
        # 初始化导出器
        self.exporters = {
            "prometheus": PrometheusExporter(),
            "json": JsonExporter()
        }
        
        # 清理任务
        self._cleanup_task: Optional[threading.Timer] = None
        self._schedule_cleanup()
    
    def store(self, points: List[MetricPoint]) -> None:
        """存储指标数据点"""
        try:
            self.storage.store(points)
        except Exception as e:
            self.logger.error(f"Error storing metrics: {e}")
    
    def query(self, query: MetricsQuery) -> List[MetricPoint]:
        """查询指标数据点"""
        try:
            return self.storage.query(query)
        except Exception as e:
            self.logger.error(f"Error querying metrics: {e}")
            return []
    
    def export(self, format: str = "prometheus", query: Optional[MetricsQuery] = None) -> str:
        """导出指标数据"""
        if format not in self.exporters:
            raise ValueError(f"Unsupported export format: {format}")
        
        points = []
        if query:
            points = self.query(query)
        else:
            # 查询最近1小时的数据
            now = time.time()
            one_hour_ago = now - 3600
            points = self.query(MetricsQuery(start_time=one_hour_ago, end_time=now))
        
        return self.exporters[format].export(points)
    
    def get_metric_names(self) -> List[str]:
        """获取所有指标名称"""
        try:
            return self.storage.get_metric_names()
        except Exception as e:
            self.logger.error(f"Error getting metric names: {e}")
            return []
    
    def cleanup(self, retention_hours: int = 24) -> int:
        """清理过期数据"""
        try:
            return self.storage.cleanup(retention_hours)
        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")
            return 0
    
    def _schedule_cleanup(self) -> None:
        """安排定期清理任务"""
        # 每小时清理一次
        self._cleanup_task = threading.Timer(3600, self._cleanup_task_handler)
        self._cleanup_task.daemon = True
        self._cleanup_task.start()
    
    def _cleanup_task_handler(self) -> None:
        """清理任务处理器"""
        try:
            self.cleanup()
        except Exception as e:
            self.logger.error(f"Error in cleanup task: {e}")
        finally:
            # 重新安排下一次清理
            self._schedule_cleanup()
    
    def shutdown(self) -> None:
        """关闭管理器"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            self._cleanup_task = None


# 全局指标管理器实例
_global_manager: Optional[MetricsManager] = None


def get_metrics_manager(
    workspace_root: str = ".",
    storage_backend: StorageBackend = StorageBackend.FILE,
    storage_options: Dict[str, Any] = None
) -> MetricsManager:
    """获取全局指标管理器实例"""
    global _global_manager
    if _global_manager is None:
        _global_manager = MetricsManager(workspace_root, storage_backend, storage_options)
    return _global_manager