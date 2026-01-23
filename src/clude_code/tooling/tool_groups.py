"""
工具分组与动态加载模块

根据用户意图动态选择工具集，减少不必要的 token 消耗。

业界对标：
- Claude Code: 根据任务类型动态加载工具
- OpenAI: 建议每请求 ≤10 个工具
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from clude_code.orchestrator.agent_loop.tool_dispatch import ToolSpec


# ============================================================
# 工具分组定义
# ============================================================

TOOL_GROUPS: dict[str, list[str]] = {
    # 最小集：仅用于纯对话
    "minimal": ["display"],
    
    # 只读操作：代码分析、搜索
    "readonly": [
        "list_dir",
        "read_file",
        "grep",
        "glob_file_search",
        "search_semantic",
    ],
    
    # 写操作：代码修改
    "write": [
        "apply_patch",
        "write_file",
        "undo_patch",
        "preview_multi_edit",
    ],
    
    # 执行操作：命令执行
    "exec": ["run_cmd"],
    
    # 网络操作：网页抓取、搜索
    "web": [
        "webfetch",
        "websearch",
        "codesearch",
    ],
    
    # 任务管理
    "task": [
        "todowrite",
        "todoread",
        "run_task",
        "get_task_status",
    ],
    
    # 实用工具
    "utility": [
        "question",
        "load_skill",
        "get_weather",
        "get_weather_forecast",
    ],
}


# ============================================================
# 意图到工具集映射
# ============================================================

INTENT_TO_GROUPS: dict[str, list[str]] = {
    # 闲聊类
    "GENERAL_CHAT": ["minimal"],
    "CAPABILITY_INQUIRY": ["minimal"],
    
    # 代码分析类
    "CODE_ANALYSIS": ["readonly"],
    "SECURITY_CONSULTING": ["readonly"],
    
    # 代码修改类
    "CODE_MODIFICATION": ["readonly", "write"],
    "PROJECT_DESIGN": ["readonly", "write"],
    
    # 执行类
    "CODE_EXECUTION": ["readonly", "write", "exec"],
    "ERROR_DIAGNOSIS": ["readonly", "exec"],
    
    # 网络类
    "WEB_RESEARCH": ["readonly", "web"],
    
    # 任务类
    "TASK_MANAGEMENT": ["readonly", "task"],
    
    # 兜底：提供常用工具
    "UNKNOWN": ["readonly", "write", "exec"],
}


# ============================================================
# 核心函数
# ============================================================

def get_tool_names_for_intent(intent: str) -> set[str]:
    """
    根据意图返回工具名称集合。
    
    Args:
        intent: 意图类别名称（如 "CODE_ANALYSIS"）
    
    Returns:
        工具名称集合
    """
    group_names = INTENT_TO_GROUPS.get(intent, INTENT_TO_GROUPS["UNKNOWN"])
    
    tool_names: set[str] = set()
    for gn in group_names:
        tool_names.update(TOOL_GROUPS.get(gn, []))
    
    return tool_names


def get_tools_for_intent(intent: str, all_tools: dict[str, "ToolSpec"]) -> list["ToolSpec"]:
    """
    根据意图返回精简的 ToolSpec 列表。
    
    Args:
        intent: 意图类别名称
        all_tools: 所有工具的字典 {name: ToolSpec}
    
    Returns:
        精简的 ToolSpec 列表
    """
    tool_names = get_tool_names_for_intent(intent)
    return [spec for name, spec in all_tools.items() if name in tool_names]


def get_tool_count_by_intent(intent: str) -> int:
    """获取某意图对应的工具数量"""
    return len(get_tool_names_for_intent(intent))


def estimate_token_savings(intent: str, total_tools: int, avg_tokens_per_tool: int = 50) -> int:
    """
    估算 Token 节省量。
    
    Args:
        intent: 意图类别
        total_tools: 总工具数
        avg_tokens_per_tool: 每工具平均 token 数（精简后约 50）
    
    Returns:
        预估节省的 token 数
    """
    intent_tools = get_tool_count_by_intent(intent)
    saved_tools = total_tools - intent_tools
    return max(0, saved_tools * avg_tokens_per_tool)


def get_groups_for_intent(intent: str) -> list[str]:
    """获取意图对应的工具组名称"""
    return INTENT_TO_GROUPS.get(intent, INTENT_TO_GROUPS["UNKNOWN"])


def list_all_groups() -> dict[str, int]:
    """列出所有工具组及其工具数量"""
    return {name: len(tools) for name, tools in TOOL_GROUPS.items()}


# ============================================================
# 调试辅助
# ============================================================

def print_tool_matrix():
    """打印意图-工具矩阵（调试用）"""
    print("意图-工具映射矩阵:")
    print("-" * 60)
    for intent, groups in INTENT_TO_GROUPS.items():
        tools = get_tool_names_for_intent(intent)
        print(f"{intent:25} | {len(tools):2} 工具 | 分组: {groups}")
    print("-" * 60)


if __name__ == "__main__":
    print_tool_matrix()

