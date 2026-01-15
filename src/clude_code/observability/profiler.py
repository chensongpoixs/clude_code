"""
性能分析工具
提供 CPU、内存和 I/O 性能分析功能
"""
from __future__ import annotations

import time
import threading
import traceback
import sys
import os
from abc import ABC, abstractmethod
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable, Union

from clude_code.observability.logger import get_logger


class ProfileType(Enum):
    """分析类型枚举"""
    CPU = "cpu"
    MEMORY = "memory"
    IO = "io"
    FUNCTION = "function"


@dataclass
class ProfileRecord:
    """性能分析记录"""
    name: str
    profile_type: ProfileType
    start_time: float
    end_time: Optional[float] = None
    duration: Optional[float] = None
    data: Dict[str, Any] = field(default_factory=dict)
    thread_id: Optional[int] = None
    call_stack: List[str] = field(default_factory=list)


class Profiler(ABC):
    """性能分析器接口"""
    
    @abstractmethod
    def start(self, name: str) -> None:
        """开始分析"""
        pass
    
    @abstractmethod
    def stop(self) -> ProfileRecord:
        """停止分析并返回记录"""
        pass
    
    @abstractmethod
    def is_running(self) -> bool:
        """检查是否正在运行"""
        pass


class CPUProfiler(Profiler):
    """CPU 性能分析器"""
    
    def __init__(self, workspace_root: str):
        self.workspace_root = workspace_root
        self.logger = get_logger(__name__, workspace_root=workspace_root)
        self._running = False
        self._start_time: Optional[float] = None
        self._name: Optional[str] = None
    
    def start(self, name: str) -> None:
        """开始 CPU 分析"""
        if self._running:
            self.logger.warning("CPU profiler is already running")
            return
        
        self._name = name
        self._start_time = time.time()
        self._running = True
        
        # 尝试使用 py-spy
        try:
            import py_spy
            self._py_spy = py_spy
            self.logger.info("Started CPU profiling with py-spy")
        except ImportError:
            self.logger.warning("py-spy not available, using fallback CPU profiling")
            self._py_spy = None
    
    def stop(self) -> ProfileRecord:
        """停止 CPU 分析"""
        if not self._running:
            self.logger.warning("CPU profiler is not running")
            return ProfileRecord(
                name="",
                profile_type=ProfileType.CPU,
                start_time=0,
                end_time=0,
                duration=0
            )
        
        end_time = time.time()
        duration = end_time - self._start_time
        self._running = False
        
        # 收集 CPU 使用情况
        cpu_data = {}
        try:
            import psutil
            cpu_data = {
                "cpu_percent": psutil.cpu_percent(interval=None),
                "cpu_count": psutil.cpu_count(),
                "cpu_freq": psutil.cpu_freq()._asdict() if psutil.cpu_freq() else {}
            }
        except ImportError:
            self.logger.warning("psutil not available for CPU profiling")
        
        record = ProfileRecord(
            name=self._name,
            profile_type=ProfileType.CPU,
            start_time=self._start_time,
            end_time=end_time,
            duration=duration,
            data=cpu_data,
            thread_id=threading.get_ident()
        )
        
        self._start_time = None
        self._name = None
        
        return record
    
    def is_running(self) -> bool:
        """检查是否正在运行"""
        return self._running


class MemoryProfiler(Profiler):
    """内存性能分析器"""
    
    def __init__(self, workspace_root: str):
        self.workspace_root = workspace_root
        self.logger = get_logger(__name__, workspace_root=workspace_root)
        self._running = False
        self._start_time: Optional[float] = None
        self._name: Optional[str] = None
        self._start_memory: Optional[Dict[str, Any]] = None
    
    def start(self, name: str) -> None:
        """开始内存分析"""
        if self._running:
            self.logger.warning("Memory profiler is already running")
            return
        
        self._name = name
        self._start_time = time.time()
        self._start_memory = self._collect_memory_info()
        self._running = True
        
        # 尝试使用 memory_profiler
        try:
            import memory_profiler
            self._memory_profiler = memory_profiler
            self.logger.info("Started memory profiling with memory_profiler")
        except ImportError:
            self.logger.warning("memory_profiler not available, using fallback memory profiling")
            self._memory_profiler = None
    
    def stop(self) -> ProfileRecord:
        """停止内存分析"""
        if not self._running:
            self.logger.warning("Memory profiler is not running")
            return ProfileRecord(
                name="",
                profile_type=ProfileType.MEMORY,
                start_time=0,
                end_time=0,
                duration=0
            )
        
        end_time = time.time()
        duration = end_time - self._start_time
        self._running = False
        
        # 收集内存使用情况
        end_memory = self._collect_memory_info()
        memory_data = {
            "start_memory": self._start_memory,
            "end_memory": end_memory,
            "memory_delta": {
                key: end_memory.get(key, 0) - self._start_memory.get(key, 0)
                for key in ["rss", "vms", "shared", "text", "lib", "data", "dirty"]
                if key in end_memory and key in self._start_memory
            }
        }
        
        record = ProfileRecord(
            name=self._name,
            profile_type=ProfileType.MEMORY,
            start_time=self._start_time,
            end_time=end_time,
            duration=duration,
            data=memory_data,
            thread_id=threading.get_ident()
        )
        
        self._start_time = None
        self._name = None
        self._start_memory = None
        
        return record
    
    def _collect_memory_info(self) -> Dict[str, Any]:
        """收集内存信息"""
        memory_info = {}
        
        try:
            import psutil
            process = psutil.Process()
            memory_info = process.memory_info()._asdict()
            memory_info.update(memory_info)
            
            # 添加内存百分比
            memory_info["percent"] = process.memory_percent()
            
            # 添加系统内存信息
            system_memory = psutil.virtual_memory()._asdict()
            memory_info["system"] = system_memory
            
        except ImportError:
            self.logger.warning("psutil not available for memory profiling")
        
        return memory_info
    
    def is_running(self) -> bool:
        """检查是否正在运行"""
        return self._running


class IOProfiler(Profiler):
    """I/O 性能分析器"""
    
    def __init__(self, workspace_root: str):
        self.workspace_root = workspace_root
        self.logger = get_logger(__name__, workspace_root=workspace_root)
        self._running = False
        self._start_time: Optional[float] = None
        self._name: Optional[str] = None
        self._start_io: Optional[Dict[str, Any]] = None
    
    def start(self, name: str) -> None:
        """开始 I/O 分析"""
        if self._running:
            self.logger.warning("I/O profiler is already running")
            return
        
        self._name = name
        self._start_time = time.time()
        self._start_io = self._collect_io_info()
        self._running = True
    
    def stop(self) -> ProfileRecord:
        """停止 I/O 分析"""
        if not self._running:
            self.logger.warning("I/O profiler is not running")
            return ProfileRecord(
                name="",
                profile_type=ProfileType.IO,
                start_time=0,
                end_time=0,
                duration=0
            )
        
        end_time = time.time()
        duration = end_time - self._start_time
        self._running = False
        
        # 收集 I/O 使用情况
        end_io = self._collect_io_info()
        io_data = {
            "start_io": self._start_io,
            "end_io": end_io,
            "io_delta": {
                key: end_io.get(key, 0) - self._start_io.get(key, 0)
                for key in ["read_count", "write_count", "read_bytes", "write_bytes"]
                if key in end_io and key in self._start_io
            }
        }
        
        record = ProfileRecord(
            name=self._name,
            profile_type=ProfileType.IO,
            start_time=self._start_time,
            end_time=end_time,
            duration=duration,
            data=io_data,
            thread_id=threading.get_ident()
        )
        
        self._start_time = None
        self._name = None
        self._start_io = None
        
        return record
    
    def _collect_io_info(self) -> Dict[str, Any]:
        """收集 I/O 信息"""
        io_info = {}
        
        try:
            import psutil
            process = psutil.Process()
            io_info = process.io_counters()._asdict()
            io_info.update(io_info)
            
            # 添加系统 I/O 信息
            system_io = psutil.disk_io_counters()._asdict()
            io_info["system"] = system_io
            
        except ImportError:
            self.logger.warning("psutil not available for I/O profiling")
        
        return io_info
    
    def is_running(self) -> bool:
        """检查是否正在运行"""
        return self._running


class FunctionProfiler(Profiler):
    """函数级性能分析器"""
    
    def __init__(self, workspace_root: str):
        self.workspace_root = workspace_root
        self.logger = get_logger(__name__, workspace_root=workspace_root)
        self._running = False
        self._start_time: Optional[float] = None
        self._name: Optional[str] = None
        self._call_stack: List[str] = []
    
    def start(self, name: str) -> None:
        """开始函数分析"""
        if self._running:
            self.logger.warning("Function profiler is already running")
            return
        
        self._name = name
        self._start_time = time.time()
        self._call_stack = self._get_call_stack()
        self._running = True
        
        # 尝试使用 cProfile
        try:
            import cProfile
            import pstats
            import io
            
            self._profile = cProfile.Profile()
            self._profile.enable()
            self._pstats = pstats.Stats(self._profile)
            self._logger.info("Started function profiling with cProfile")
        except ImportError:
            self.logger.warning("cProfile not available, using fallback function profiling")
            self._profile = None
    
    def stop(self) -> ProfileRecord:
        """停止函数分析"""
        if not self._running:
            self.logger.warning("Function profiler is not running")
            return ProfileRecord(
                name="",
                profile_type=ProfileType.FUNCTION,
                start_time=0,
                end_time=0,
                duration=0
            )
        
        end_time = time.time()
        duration = end_time - self._start_time
        self._running = False
        
        # 收集函数调用统计
        function_data = {}
        
        if self._profile:
            self._profile.disable()
            
            # 获取统计信息
            stats_stream = io.StringIO()
            self._pstats.sort_stats('cumulative').print_stats(20, stream=stats_stream)
            stats_text = stats_stream.getvalue()
            
            function_data = {
                "profile_output": stats_text,
                "call_count": self._pstats.total_calls,
                "primitive_calls": self._pstats.prim_calls,
                "total_time": self._pstats.total_tt
            }
        
        record = ProfileRecord(
            name=self._name,
            profile_type=ProfileType.FUNCTION,
            start_time=self._start_time,
            end_time=end_time,
            duration=duration,
            data=function_data,
            thread_id=threading.get_ident(),
            call_stack=self._call_stack
        )
        
        self._start_time = None
        self._name = None
        self._call_stack = []
        
        return record
    
    def _get_call_stack(self) -> List[str]:
        """获取调用栈"""
        stack = []
        try:
            for frame_info in traceback.extract_stack():
                if frame_info.filename:
                    # 只包含项目文件
                    if self.workspace_root in frame_info.filename:
                        filename = Path(frame_info.filename).name
                        function = frame_info.name
                        line_no = frame_info.lineno
                        stack.append(f"{filename}:{function}:{line_no}")
        except Exception as e:
            self.logger.error(f"Error getting call stack: {e}")
        
        return stack[-10:]  # 只保留最近10层
    
    def is_running(self) -> bool:
        """检查是否正在运行"""
        return self._running


class ProfileManager:
    """性能分析管理器"""
    
    def __init__(self, workspace_root: str):
        self.workspace_root = workspace_root
        self.logger = get_logger(__name__, workspace_root=workspace_root)
        
        # 创建存储目录
        self.storage_dir = Path(workspace_root) / ".clude" / "profiles"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        # 创建分析器
        self.profilers = {
            ProfileType.CPU: CPUProfiler(workspace_root),
            ProfileType.MEMORY: MemoryProfiler(workspace_root),
            ProfileType.IO: IOProfiler(workspace_root),
            ProfileType.FUNCTION: FunctionProfiler(workspace_root)
        }
        
        # 分析记录
        self.records: List[ProfileRecord] = []
        self._lock = threading.Lock()
    
    def start_profiling(self, name: str, profile_type: ProfileType) -> bool:
        """开始指定类型的分析"""
        profiler = self.profilers[profile_type]
        if profiler.is_running():
            self.logger.warning(f"{profile_type.value} profiler is already running")
            return False
        
        try:
            profiler.start(name)
            self.logger.info(f"Started {profile_type.value} profiling: {name}")
            return True
        except Exception as e:
            self.logger.error(f"Error starting {profile_type.value} profiling: {e}")
            return False
    
    def stop_profiling(self, profile_type: ProfileType) -> Optional[ProfileRecord]:
        """停止指定类型的分析"""
        profiler = self.profilers[profile_type]
        if not profiler.is_running():
            self.logger.warning(f"{profile_type.value} profiler is not running")
            return None
        
        try:
            record = profiler.stop()
            with self._lock:
                self.records.append(record)
            
            self.logger.info(f"Stopped {profile_type.value} profiling: {record.name}")
            return record
        except Exception as e:
            self.logger.error(f"Error stopping {profile_type.value} profiling: {e}")
            return None
    
    def get_records(self, profile_type: Optional[ProfileType] = None, limit: Optional[int] = None) -> List[ProfileRecord]:
        """获取分析记录"""
        with self._lock:
            records = self.records.copy()
        
        # 按类型过滤
        if profile_type:
            records = [r for r in records if r.profile_type == profile_type]
        
        # 按时间排序
        records.sort(key=lambda r: r.start_time, reverse=True)
        
        # 限制数量
        if limit:
            records = records[:limit]
        
        return records
    
    def save_records(self, profile_type: Optional[ProfileType] = None) -> None:
        """保存分析记录到文件"""
        records = self.get_records(profile_type)
        
        if not records:
            return
        
        # 按类型分组保存
        grouped = {}
        for record in records:
            if record.profile_type not in grouped:
                grouped[record.profile_type] = []
            grouped[record.profile_type].append(record)
        
        # 保存每种类型
        for ptype, ptype_records in grouped.items():
            filename = f"{ptype.value}_profiles.json"
            filepath = self.storage_dir / filename
            
            data = []
            for record in ptype_records:
                data.append({
                    "name": record.name,
                    "profile_type": record.profile_type.value,
                    "start_time": record.start_time,
                    "end_time": record.end_time,
                    "duration": record.duration,
                    "data": record.data,
                    "thread_id": record.thread_id,
                    "call_stack": record.call_stack
                })
            
            try:
                import json
                with open(filepath, 'w') as f:
                    json.dump(data, f, indent=2)
                
                self.logger.info(f"Saved {len(data)} {ptype.value} profiles to {filepath}")
            except Exception as e:
                self.logger.error(f"Error saving {ptype.value} profiles: {e}")
    
    def clear_records(self, profile_type: Optional[ProfileType] = None) -> int:
        """清除分析记录"""
        with self._lock:
            if profile_type:
                old_count = len(self.records)
                self.records = [r for r in self.records if r.profile_type != profile_type]
                removed_count = old_count - len(self.records)
            else:
                removed_count = len(self.records)
                self.records.clear()
        
        self.logger.info(f"Cleared {removed_count} profile records")
        return removed_count


# 全局分析管理器实例
_global_manager: Optional[ProfileManager] = None


def get_profile_manager(workspace_root: str = ".") -> ProfileManager:
    """获取全局分析管理器实例"""
    global _global_manager
    if _global_manager is None:
        _global_manager = ProfileManager(workspace_root)
    return _global_manager


# 便捷装饰器和函数
def profile(
    name: Optional[str] = None,
    profile_type: ProfileType = ProfileType.FUNCTION,
    workspace_root: str = "."
):
    """性能分析装饰器"""
    def decorator(func: Callable) -> Callable:
        profile_name = name or f"{func.__module__}.{func.__name__}"
        
        def wrapper(*args, **kwargs):
            manager = get_profile_manager(workspace_root)
            if manager.start_profiling(profile_name, profile_type):
                try:
                    result = func(*args, **kwargs)
                    return result
                finally:
                    manager.stop_profiling(profile_type)
            else:
                # 分析器启动失败，直接执行函数
                return func(*args, **kwargs)
        
        return wrapper
    return decorator


@contextmanager
def profile_context(
    name: str,
    profile_type: ProfileType = ProfileType.FUNCTION,
    workspace_root: str = "."
):
    """性能分析上下文管理器"""
    manager = get_profile_manager(workspace_root)
    if manager.start_profiling(name, profile_type):
        try:
            yield
        finally:
            manager.stop_profiling(profile_type)
    else:
        # 分析器启动失败，直接执行
        yield


def start_profile(name: str, profile_type: ProfileType = ProfileType.FUNCTION, workspace_root: str = ".") -> bool:
    """开始性能分析"""
    manager = get_profile_manager(workspace_root)
    return manager.start_profiling(name, profile_type)


def stop_profile(profile_type: ProfileType = ProfileType.FUNCTION, workspace_root: str = ".") -> Optional[ProfileRecord]:
    """停止性能分析"""
    manager = get_profile_manager(workspace_root)
    return manager.stop_profiling(profile_type)


def get_profile_records(profile_type: Optional[ProfileType] = None, limit: Optional[int] = None, workspace_root: str = ".") -> List[ProfileRecord]:
    """获取性能分析记录"""
    manager = get_profile_manager(workspace_root)
    return manager.get_records(profile_type, limit)


def save_profile_records(profile_type: Optional[ProfileType] = None, workspace_root: str = ".") -> None:
    """保存性能分析记录"""
    manager = get_profile_manager(workspace_root)
    manager.save_records(profile_type)


def clear_profile_records(profile_type: Optional[ProfileType] = None, workspace_root: str = ".") -> int:
    """清除性能分析记录"""
    manager = get_profile_manager(workspace_root)
    return manager.clear_records(profile_type)