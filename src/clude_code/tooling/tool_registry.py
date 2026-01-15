"""
工具注册表管理器
参考Claude Code的最佳实践，实现工具的动态注册、分类和优先级管理
"""
import logging
from typing import Dict, List, Optional, Set, Any, Callable
from dataclasses import dataclass, field
from enum import Enum

from .tool_dispatch import ToolSpec


logger = logging.getLogger(__name__)


class ToolCategory(Enum):
    """工具分类枚举"""
    FILE = "file"          # 文件操作
    SEARCH = "search"      # 搜索操作
    EXEC = "exec"          # 执行操作
    SYSTEM = "system"      # 系统操作
    NETWORK = "network"    # 网络操作
    ANALYSIS = "analysis"  # 分析操作
    UTILITY = "utility"    # 工具操作


@dataclass
class ToolMetrics:
    """工具性能指标"""
    call_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    average_duration: float = 0.0
    last_used: Optional[float] = None
    error_rate: float = 0.0


class ToolRegistry:
    """
    工具注册表管理器
    参考Claude Code，实现工具的集中管理和动态注册
    """

    def __init__(self):
        self._tools: Dict[str, ToolSpec] = {}
        self._categories: Dict[str, List[str]] = {}
        self._metrics: Dict[str, ToolMetrics] = {}
        self._listeners: List[Callable[[str, ToolSpec], None]] = []
        self._deprecated_tools: Set[str] = set()

    def register_tool(self, tool_spec: ToolSpec) -> None:
        """
        注册工具

        Args:
            tool_spec: 工具规范
        """
        if tool_spec.name in self._tools:
            logger.warning(f"工具 '{tool_spec.name}' 已被注册，将覆盖")

        # 检查是否已废弃
        if tool_spec.deprecated:
            self._deprecated_tools.add(tool_spec.name)
            logger.warning(f"注册已废弃的工具: {tool_spec.name}")

        # 注册工具
        self._tools[tool_spec.name] = tool_spec

        # 添加到分类
        category = tool_spec.category
        if category not in self._categories:
            self._categories[category] = []
        if tool_spec.name not in self._categories[category]:
            self._categories[category].append(tool_spec.name)

        # 初始化指标
        self._metrics[tool_spec.name] = ToolMetrics()

        # 通知监听器
        for listener in self._listeners:
            try:
                listener("register", tool_spec)
            except Exception as e:
                logger.error(f"工具注册监听器错误: {e}")

        logger.info(f"已注册工具: {tool_spec.name} (分类: {category})")

    def unregister_tool(self, tool_name: str) -> bool:
        """
        注销工具

        Args:
            tool_name: 工具名称

        Returns:
            是否成功注销
        """
        if tool_name not in self._tools:
            logger.warning(f"工具 '{tool_name}' 未注册")
            return False

        tool_spec = self._tools[tool_name]

        # 从分类中移除
        category = tool_spec.category
        if category in self._categories and tool_name in self._categories[category]:
            self._categories[category].remove(tool_name)

        # 移除工具和指标
        del self._tools[tool_name]
        if tool_name in self._metrics:
            del self._metrics[tool_name]

        # 从废弃列表中移除
        self._deprecated_tools.discard(tool_name)

        # 通知监听器
        for listener in self._listeners:
            try:
                listener("unregister", tool_spec)
            except Exception as e:
                logger.error(f"工具注销监听器错误: {e}")

        logger.info(f"已注销工具: {tool_name}")
        return True

    def get_tool(self, tool_name: str) -> Optional[ToolSpec]:
        """
        获取工具规范

        Args:
            tool_name: 工具名称

        Returns:
            工具规范，如果不存在返回None
        """
        return self._tools.get(tool_name)

    def list_tools(self,
                   category: Optional[str] = None,
                   callable_only: bool = False,
                   include_deprecated: bool = False) -> List[ToolSpec]:
        """
        列出工具

        Args:
            category: 分类过滤，如果为None则返回所有
            callable_only: 只返回可调用的工具
            include_deprecated: 是否包含已废弃的工具

        Returns:
            工具规范列表，按优先级排序
        """
        tools = []

        tool_names = []
        if category:
            tool_names = self._categories.get(category, [])
        else:
            tool_names = list(self._tools.keys())

        for name in tool_names:
            tool = self._tools.get(name)
            if not tool:
                continue

            # 过滤条件
            if callable_only and not tool.callable_by_model:
                continue
            if not include_deprecated and tool.deprecated:
                continue

            tools.append(tool)

        # 按优先级排序（高优先级在前）
        tools.sort(key=lambda t: t.priority, reverse=True)

        return tools

    def get_categories(self) -> Dict[str, int]:
        """
        获取所有分类及其工具数量

        Returns:
            分类到数量的映射
        """
        return {cat: len(names) for cat, names in self._categories.items()}

    def is_tool_available(self, tool_name: str) -> bool:
        """
        检查工具是否可用

        Args:
            tool_name: 工具名称

        Returns:
            是否可用
        """
        tool = self.get_tool(tool_name)
        if not tool:
            return False

        if tool.deprecated:
            return False

        # 检查外部依赖
        # 这里可以扩展为实际的依赖检查逻辑
        return True

    def update_metrics(self, tool_name: str, success: bool, duration: float) -> None:
        """
        更新工具性能指标

        Args:
            tool_name: 工具名称
            success: 是否成功
            duration: 执行时长（秒）
        """
        if tool_name not in self._metrics:
            self._metrics[tool_name] = ToolMetrics()

        metrics = self._metrics[tool_name]
        metrics.call_count += 1
        metrics.last_used = duration  # 这里应该用当前时间戳

        if success:
            metrics.success_count += 1
        else:
            metrics.failure_count += 1

        # 更新平均时长
        total_duration = metrics.average_duration * (metrics.call_count - 1) + duration
        metrics.average_duration = total_duration / metrics.call_count

        # 更新错误率
        metrics.error_rate = metrics.failure_count / metrics.call_count

    def get_metrics(self, tool_name: str) -> Optional[ToolMetrics]:
        """
        获取工具性能指标

        Args:
            tool_name: 工具名称

        Returns:
            性能指标
        """
        return self._metrics.get(tool_name)

    def get_popular_tools(self, limit: int = 10) -> List[tuple[str, ToolMetrics]]:
        """
        获取最热门的工具

        Args:
            limit: 返回数量限制

        Returns:
            (工具名, 指标) 元组列表，按使用次数排序
        """
        tool_metrics = [(name, metrics) for name, metrics in self._metrics.items()]
        tool_metrics.sort(key=lambda x: x[1].call_count, reverse=True)
        return tool_metrics[:limit]

    def add_listener(self, listener: Callable[[str, ToolSpec], None]) -> None:
        """
        添加监听器

        Args:
            listener: 监听器函数，参数为 (action, tool_spec)
        """
        self._listeners.append(listener)

    def remove_listener(self, listener: Callable[[str, ToolSpec], None]) -> None:
        """
        移除监听器

        Args:
            listener: 要移除的监听器函数
        """
        if listener in self._listeners:
            self._listeners.remove(listener)

    def validate_tool_args(self, tool_name: str, args: Dict[str, Any]) -> tuple[bool, str]:
        """
        验证工具参数

        Args:
            tool_name: 工具名称
            args: 参数字典

        Returns:
            (是否有效, 错误消息)
        """
        tool = self.get_tool(tool_name)
        if not tool:
            return False, f"工具 '{tool_name}' 不存在"

        try:
            is_valid, result = tool.validate_args(args)
            if not is_valid:
                return False, str(result)
            return True, ""
        except Exception as e:
            return False, f"参数验证失败: {e}"

    def get_tool_dependencies(self, tool_name: str) -> tuple[Set[str], Set[str]]:
        """
        获取工具的依赖

        Args:
            tool_name: 工具名称

        Returns:
            (必需依赖, 可选依赖)
        """
        tool = self.get_tool(tool_name)
        if not tool:
            return set(), set()

        return tool.external_bins_required, tool.external_bins_optional


# 全局工具注册表实例
_tool_registry: Optional[ToolRegistry] = None

def get_tool_registry() -> ToolRegistry:
    """获取全局工具注册表实例"""
    global _tool_registry
    if _tool_registry is None:
        _tool_registry = ToolRegistry()
        # 初始化所有内置工具
        _initialize_builtin_tools(_tool_registry)
    return _tool_registry

def _initialize_builtin_tools(registry: ToolRegistry) -> None:
    """初始化内置工具"""
    from clude_code.orchestrator.agent_loop.tool_dispatch import iter_tool_specs

    for tool_spec in iter_tool_specs():
        try:
            registry.register_tool(tool_spec)
        except Exception as e:
            logger.error(f"注册工具 '{tool_spec.name}' 失败: {e}")