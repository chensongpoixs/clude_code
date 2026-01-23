# 工具模块优化分析报告

> **创建时间**: 2026-01-23  
> **分析目标**: 对标业界最佳实践，识别问题点，提出 Token 节省方案

---

## 目录

1. [当前架构分析](#1-当前架构分析)
2. [业界对标](#2-业界对标)
3. [问题诊断](#3-问题诊断)
4. [Token 节省方案](#4-token-节省方案)
5. [优化实现细节](#5-优化实现细节)
6. [实施优先级](#6-实施优先级)

---

## 1. 当前架构分析

### 1.1 模块结构

```
src/clude_code/tooling/
├── local_tools.py          # LocalTools 类：工具调用入口
├── tool_registry.py        # ToolRegistry：工具注册与管理
├── feedback.py             # summarize_tool_result：结果摘要与压缩
├── types.py                # ToolResult、ToolError 类型定义
├── tools/                  # 具体工具实现
│   ├── read_file.py
│   ├── grep.py
│   ├── patching.py
│   └── ...
└── ...

src/clude_code/orchestrator/agent_loop/
└── tool_dispatch.py        # ToolSpec 定义 + Handler 映射 + dispatch_tool
```

### 1.2 工具调用流程

```
LLM Output → parse_tool_call → dispatch_tool → handler → ToolResult
                                                            │
                                                            ▼
                                              summarize_tool_result (feedback.py)
                                                            │
                                                            ▼
                                              format_feedback_message → LLM
```

### 1.3 当前工具数量

| 类别 | 工具 |
|------|------|
| 文件操作 | list_dir, read_file, write_file, apply_patch, undo_patch |
| 搜索 | grep, glob_file_search, search_semantic |
| 执行 | run_cmd |
| 网络 | webfetch, websearch, codesearch |
| 任务管理 | todowrite, todoread, run_task, get_task_status |
| 交互 | display, question |
| 其他 | load_skill, get_weather, get_weather_forecast |

**总计**: 约 20 个工具，每个工具的 ToolSpec 平均消耗 **150-300 tokens**。

---

## 2. 业界对标

### 2.1 Claude Code（Anthropic）

| 特性 | Claude Code | 当前项目 | 差距 |
|------|-------------|---------|------|
| 工具 Schema 精简 | ✅ 最小化必需参数 | ⚠️ 冗余描述 | 中 |
| 动态工具加载 | ✅ 按需加载 | ❌ 全量加载 | 高 |
| 结果压缩 | ✅ 智能摘要 | ✅ 已实现 | 低 |
| 工具分组 | ✅ 按角色分组 | ❌ 扁平列表 | 中 |
| 缓存机制 | ✅ 结果缓存 | ⚠️ 部分 | 中 |

### 2.2 Cursor

| 特性 | Cursor | 当前项目 | 差距 |
|------|--------|---------|------|
| 语义工具选择 | ✅ 根据任务推荐 | ❌ 全量暴露 | 高 |
| 渐进式加载 | ✅ 先给核心工具 | ❌ 一次性加载 | 高 |
| 工具使用统计 | ✅ 热度排序 | ✅ 已实现 | 低 |

### 2.3 OpenAI Function Calling

| 特性 | OpenAI | 当前项目 | 差距 |
|------|--------|---------|------|
| Schema 格式 | JSON Schema 精简版 | ✅ 兼容 | 低 |
| 工具数量建议 | ≤10 个/请求 | ⚠️ 20 个 | 高 |
| 描述长度建议 | ≤100 字符 | ⚠️ 200+ 字符 | 中 |

---

## 3. 问题诊断

### 3.1 🔴 高优先级问题

#### P1: 工具 Schema 过于冗长

**当前问题**:
- 每个 ToolSpec 的 `description` 平均 200+ 字符
- 20 个工具全量注入 System Prompt
- 估算消耗: **3000-5000 tokens**

**示例（当前）**:
```python
description=(
    "用于在工作区内按正则搜索文本内容（Grep / Ripgrep）。支持 C/C++/Java 等多种语言的自动后缀匹配。\n"
    "如果你在寻找特定语言的定义（如 C++ 类或 Java 方法），指定 'language' 参数将极大提高准确率。"
)
# 约 120 字符 = ~40 tokens
```

**业界标准（Claude Code）**:
```python
description="Search files with regex pattern"
# 约 35 字符 = ~10 tokens
```

**节省潜力**: 每个工具节省 30 tokens × 20 工具 = **600 tokens**

#### P2: 全量工具注入

**当前问题**:
- 所有 20 个工具在每次请求都注入 System Prompt
- 用户仅询问"你好"时也加载 grep、apply_patch 等工具

**业界做法（动态工具集）**:
```
意图: GENERAL_CHAT → 工具集: [display]
意图: CODE_ANALYSIS → 工具集: [read_file, grep, search_semantic]
意图: CODE_MODIFICATION → 工具集: [read_file, grep, apply_patch, write_file]
```

**节省潜力**: 根据意图减少 50-80% 工具 = **1500-4000 tokens**

#### P3: 工具结果冗余

**当前问题**:
- `feedback.py` 已做压缩，但某些场景仍返回过多数据
- `read_file` 返回完整文件内容而非语义窗口
- `grep` 返回 20 条结果，每条 200 字符预览

**示例（当前 grep 返回）**:
```json
{
  "hits": [
    {"path": "a.py", "line": 10, "preview": "def foo(): # 200 chars..."},
    {"path": "b.py", "line": 20, "preview": "def bar(): # 200 chars..."},
    // ... 20 条
  ]
}
```

**业界做法（分层摘要）**:
```json
{
  "summary": "Found 45 matches in 8 files",
  "top_hits": [
    {"path": "a.py", "lines": "10,15,20", "context": "function definitions"}
  ],
  "full_results_available": true
}
```

**节省潜力**: 减少 50% 结果体积 = **500-2000 tokens/次**

### 3.2 🟡 中优先级问题

#### P4: 缺乏工具使用热度优化

**当前状态**: `ToolRegistry` 有 `get_popular_tools()` 但未用于 Prompt 优化

**优化方案**: 高频工具排在前面，低频工具简化描述

#### P5: 缺乏工具依赖推断

**当前状态**: LLM 可能调用 `apply_patch` 而未先 `read_file`

**优化方案**: 提供工具链建议（Tool Chain Hints）

#### P6: 工具参数默认值未在 Schema 层面优化

**当前状态**: 默认值在 handler 和 schema 中重复定义

**优化方案**: 统一在 schema 定义，handler 仅负责执行

---

## 4. Token 节省方案

### 4.1 方案总览

| 方案 | 预估节省 | 实现复杂度 | 优先级 |
|------|---------|-----------|--------|
| A: 工具描述精简 | 600 tokens | 低 | P0 |
| B: 动态工具集 | 1500-4000 tokens | 中 | P0 |
| C: 结果分层压缩 | 500-2000 tokens/次 | 中 | P1 |
| D: 工具热度排序 | 100-300 tokens | 低 | P2 |
| E: 工具链提示 | 间接节省 | 中 | P2 |
| F: 参数默认值优化 | 100 tokens | 低 | P3 |

### 4.2 方案 A: 工具描述精简

#### 4.2.1 精简规则

1. **Summary**: ≤50 字符，纯功能描述
2. **Description**: ≤100 字符，仅关键提示
3. **参数描述**: ≤30 字符

#### 4.2.2 精简示例

**Before**:
```python
ToolSpec(
    name="grep",
    summary="全能跨语言代码搜索器。",
    description=(
        "用于在工作区内按正则搜索文本内容（Grep / Ripgrep）。支持 C/C++/Java 等多种语言的自动后缀匹配。\n"
        "如果你在寻找特定语言的定义（如 C++ 类或 Java 方法），指定 'language' 参数将极大提高准确率。"
    ),
    args_schema=_obj_schema(
        properties={
            "pattern": {"type": "string", "description": "正则表达式模式，支持标准正则语法"},
            "path": {"type": "string", "default": ".", "description": "搜索路径（相对工作区）"},
            "language": {"type": "string", "default": "all", "description": "语言类型：cpp/java/python/all"},
            "include_glob": {"type": ["string", "null"], "description": "额外 glob 过滤，如 *.cpp"},
            "ignore_case": {"type": "boolean", "default": False, "description": "是否忽略大小写"},
            "max_hits": {"type": "integer", "default": 200, "description": "最大返回条目数"},
        },
        required=["pattern"],
    ),
)
```

**After**:
```python
ToolSpec(
    name="grep",
    summary="正则搜索代码",
    description="在工作区按正则搜索。支持 language 过滤。",
    args_schema=_obj_schema(
        properties={
            "pattern": {"type": "string", "description": "正则模式"},
            "path": {"type": "string", "default": "."},
            "language": {"type": "string", "default": "all", "enum": ["all","cpp","java","python","go","rust","js","ts"]},
            "ignore_case": {"type": "boolean", "default": False},
            "max_hits": {"type": "integer", "default": 100},
        },
        required=["pattern"],
    ),
)
```

**Token 对比**:
- Before: ~120 tokens
- After: ~50 tokens
- 节省: **70 tokens/工具**

### 4.3 方案 B: 动态工具集

#### 4.3.1 工具分组定义

```python
# src/clude_code/tooling/tool_groups.py

TOOL_GROUPS = {
    "minimal": ["display"],  # 纯对话
    "readonly": ["list_dir", "read_file", "grep", "glob_file_search", "search_semantic"],
    "write": ["apply_patch", "write_file", "undo_patch"],
    "exec": ["run_cmd"],
    "web": ["webfetch", "websearch", "codesearch"],
    "task": ["todowrite", "todoread", "run_task", "get_task_status"],
    "utility": ["question", "load_skill", "get_weather", "get_weather_forecast"],
}

# 意图到工具集的映射
INTENT_TO_TOOLS = {
    "GENERAL_CHAT": ["minimal"],
    "CODE_ANALYSIS": ["readonly"],
    "CODE_MODIFICATION": ["readonly", "write"],
    "CODE_EXECUTION": ["readonly", "write", "exec"],
    "WEB_RESEARCH": ["readonly", "web"],
    "TASK_MANAGEMENT": ["readonly", "task"],
}
```

#### 4.3.2 动态注入逻辑

```python
# 在 AgentLoop._build_system_prompt() 中

def _get_tools_for_intent(self, intent: str) -> list[ToolSpec]:
    """根据意图返回精简的工具集"""
    from clude_code.tooling.tool_groups import INTENT_TO_TOOLS, TOOL_GROUPS
    
    group_names = INTENT_TO_TOOLS.get(intent, ["readonly"])
    tool_names = set()
    for gn in group_names:
        tool_names.update(TOOL_GROUPS.get(gn, []))
    
    return [spec for spec in iter_tool_specs() if spec.name in tool_names]

def _build_tools_prompt(self, intent: str) -> str:
    """生成精简的工具提示"""
    tools = self._get_tools_for_intent(intent)
    
    lines = ["## 可用工具"]
    for t in tools:
        # 紧凑格式：一行一个工具
        args_hint = ", ".join(f"{k}={v.get('default','?')}" for k, v in t.args_schema.get("properties", {}).items())
        lines.append(f"- {t.name}({args_hint}): {t.summary}")
    
    return "\n".join(lines)
```

#### 4.3.3 效果对比

| 场景 | 当前工具数 | 优化后 | Token 节省 |
|------|-----------|--------|-----------|
| 闲聊 | 20 | 1 | ~2800 |
| 代码分析 | 20 | 5 | ~2100 |
| 代码修改 | 20 | 8 | ~1680 |
| 全功能 | 20 | 20 | 0 |

### 4.4 方案 C: 结果分层压缩

#### 4.4.1 三层压缩策略

```python
# src/clude_code/tooling/feedback.py

class ResultCompressor:
    """工具结果分层压缩器"""
    
    # 压缩级别
    LEVEL_SUMMARY = "summary"      # 仅摘要（最省 token）
    LEVEL_COMPACT = "compact"      # 紧凑（默认）
    LEVEL_DETAILED = "detailed"    # 详细（首次调用或显式请求）
    
    def compress(self, tool: str, result: ToolResult, level: str = "compact") -> dict:
        if not result.ok:
            return {"tool": tool, "ok": False, "error": result.error}
        
        if level == self.LEVEL_SUMMARY:
            return self._to_summary(tool, result)
        elif level == self.LEVEL_COMPACT:
            return self._to_compact(tool, result)
        else:
            return self._to_detailed(tool, result)
    
    def _to_summary(self, tool: str, result: ToolResult) -> dict:
        """仅返回统计摘要"""
        payload = result.payload or {}
        
        if tool == "grep":
            hits = payload.get("hits", [])
            files = set(h.get("path") for h in hits if isinstance(h, dict))
            return {
                "tool": tool,
                "ok": True,
                "summary": f"Found {len(hits)} matches in {len(files)} files",
                "has_more": len(hits) > 0,
            }
        
        if tool == "read_file":
            text = payload.get("text", "")
            return {
                "tool": tool,
                "ok": True,
                "summary": f"Read {len(text)} chars, {len(text.splitlines())} lines",
                "has_more": True,
            }
        
        # 其他工具...
        return {"tool": tool, "ok": True, "summary": "completed"}
    
    def _to_compact(self, tool: str, result: ToolResult) -> dict:
        """返回紧凑结果（当前 summarize_tool_result 的增强版）"""
        # 复用现有逻辑，但进一步压缩
        # - grep: 仅 top 5 hits，preview 限制 100 字符
        # - read_file: 仅语义窗口，限制 2000 字符
        # - list_dir: 仅 top 10 items
        pass
    
    def _to_detailed(self, tool: str, result: ToolResult) -> dict:
        """返回完整结果（首次调用或显式请求）"""
        return {"tool": tool, "ok": True, **result.payload}
```

#### 4.4.2 自适应压缩级别

```python
def get_compression_level(tool: str, context_utilization: float, call_count: int) -> str:
    """根据上下文使用率和调用次数决定压缩级别"""
    
    # 上下文紧张时强制摘要
    if context_utilization > 0.8:
        return ResultCompressor.LEVEL_SUMMARY
    
    # 首次调用给详细结果
    if call_count == 0:
        return ResultCompressor.LEVEL_DETAILED
    
    # 重复调用给紧凑结果
    if call_count >= 2:
        return ResultCompressor.LEVEL_SUMMARY
    
    return ResultCompressor.LEVEL_COMPACT
```

### 4.5 方案 D: 工具热度排序

```python
def get_tools_sorted_by_usage(tools: list[ToolSpec], metrics: dict[str, ToolMetrics]) -> list[ToolSpec]:
    """按使用热度排序工具，高频工具在前"""
    def sort_key(t: ToolSpec) -> tuple:
        m = metrics.get(t.name)
        if not m:
            return (0, t.priority)
        return (m.call_count, t.priority)
    
    return sorted(tools, key=sort_key, reverse=True)

def generate_tools_prompt_with_priority(tools: list[ToolSpec], metrics: dict) -> str:
    """生成带优先级提示的工具列表"""
    sorted_tools = get_tools_sorted_by_usage(tools, metrics)
    
    lines = ["## 工具（按使用频率排序）"]
    for i, t in enumerate(sorted_tools):
        # 前 5 个工具完整描述
        if i < 5:
            lines.append(f"### {t.name}")
            lines.append(f"{t.summary}")
            lines.append(f"参数: {t.example_args}")
        else:
            # 后续工具仅名称
            lines.append(f"- {t.name}: {t.summary}")
    
    return "\n".join(lines)
```

---

## 5. 优化实现细节

### 5.1 工具描述精简（方案 A）

#### 5.1.1 修改文件

- `src/clude_code/orchestrator/agent_loop/tool_dispatch.py`

#### 5.1.2 实现步骤

1. 定义精简描述规范
2. 逐个工具重写 summary/description
3. 简化 args_schema 中的 description
4. 验证 LLM 理解度（回归测试）

#### 5.1.3 精简后的工具描述模板

```python
# 工具描述精简模板
TOOL_DESCRIPTIONS = {
    "list_dir": ("列出目录", "查看目录内容"),
    "read_file": ("读取文件", "支持 offset/limit 分段"),
    "glob_file_search": ("按名搜索文件", "支持 ** 递归"),
    "grep": ("正则搜索代码", "支持语言过滤"),
    "apply_patch": ("补丁编辑", "基于上下文替换"),
    "undo_patch": ("回滚补丁", "基于 undo_id"),
    "write_file": ("写入文件", "支持追加/插入"),
    "run_cmd": ("执行命令", "需确认"),
    "search_semantic": ("语义搜索", "向量 RAG"),
    "display": ("显示消息", "输出到 UI"),
    "webfetch": ("获取网页", "转 Markdown"),
    "websearch": ("网页搜索", "DuckDuckGo"),
    "codesearch": ("代码搜索", "GitHub/Sourcegraph"),
    "todowrite": ("创建任务", ""),
    "todoread": ("读取任务", ""),
    "question": ("向用户提问", ""),
    "load_skill": ("加载技能", ""),
    "run_task": ("运行子任务", ""),
    "get_task_status": ("获取任务状态", ""),
    "get_weather": ("获取天气", ""),
    "get_weather_forecast": ("获取天气预报", ""),
}
```

### 5.2 动态工具集（方案 B）

#### 5.2.1 新增文件

- `src/clude_code/tooling/tool_groups.py`

#### 5.2.2 完整实现

```python
# src/clude_code/tooling/tool_groups.py

from __future__ import annotations
from typing import TYPE_CHECKING
from enum import Enum

if TYPE_CHECKING:
    from clude_code.orchestrator.agent_loop.tool_dispatch import ToolSpec


class ToolGroup(Enum):
    """工具分组"""
    MINIMAL = "minimal"      # 仅 display
    READONLY = "readonly"    # 只读操作
    WRITE = "write"          # 写文件
    EXEC = "exec"            # 执行命令
    WEB = "web"              # 网络操作
    TASK = "task"            # 任务管理
    UTILITY = "utility"      # 实用工具


# 工具分组定义
TOOL_GROUPS: dict[str, list[str]] = {
    "minimal": ["display"],
    "readonly": ["list_dir", "read_file", "grep", "glob_file_search", "search_semantic"],
    "write": ["apply_patch", "write_file", "undo_patch"],
    "exec": ["run_cmd"],
    "web": ["webfetch", "websearch", "codesearch"],
    "task": ["todowrite", "todoread", "run_task", "get_task_status"],
    "utility": ["question", "load_skill", "get_weather", "get_weather_forecast"],
}


# 意图到工具集的映射
INTENT_TO_GROUPS: dict[str, list[str]] = {
    "GENERAL_CHAT": ["minimal"],
    "CAPABILITY_INQUIRY": ["minimal"],
    "CODE_ANALYSIS": ["readonly"],
    "CODE_MODIFICATION": ["readonly", "write"],
    "CODE_EXECUTION": ["readonly", "write", "exec"],
    "ERROR_DIAGNOSIS": ["readonly", "exec"],
    "WEB_RESEARCH": ["readonly", "web"],
    "TASK_MANAGEMENT": ["readonly", "task"],
    "SECURITY_CONSULTING": ["readonly"],
    "PROJECT_DESIGN": ["readonly", "write"],
    # 默认
    "UNKNOWN": ["readonly", "write", "exec"],
}


def get_tools_for_intent(intent: str, all_tools: dict[str, "ToolSpec"]) -> list["ToolSpec"]:
    """
    根据意图返回精简的工具集。
    
    Args:
        intent: 意图类别名称
        all_tools: 所有工具的字典 {name: ToolSpec}
    
    Returns:
        精简的 ToolSpec 列表
    """
    group_names = INTENT_TO_GROUPS.get(intent, INTENT_TO_GROUPS["UNKNOWN"])
    
    tool_names: set[str] = set()
    for gn in group_names:
        tool_names.update(TOOL_GROUPS.get(gn, []))
    
    return [spec for name, spec in all_tools.items() if name in tool_names]


def get_tool_count_by_intent(intent: str) -> int:
    """获取某意图对应的工具数量"""
    group_names = INTENT_TO_GROUPS.get(intent, INTENT_TO_GROUPS["UNKNOWN"])
    tool_names: set[str] = set()
    for gn in group_names:
        tool_names.update(TOOL_GROUPS.get(gn, []))
    return len(tool_names)


def estimate_token_savings(intent: str, total_tools: int, avg_tokens_per_tool: int = 150) -> int:
    """估算 Token 节省量"""
    intent_tools = get_tool_count_by_intent(intent)
    saved_tools = total_tools - intent_tools
    return saved_tools * avg_tokens_per_tool
```

#### 5.2.3 AgentLoop 集成

```python
# src/clude_code/orchestrator/agent_loop/agent_loop.py

from clude_code.tooling.tool_groups import get_tools_for_intent

def _build_tools_prompt(self, intent: str) -> str:
    """根据意图生成精简的工具提示"""
    from clude_code.orchestrator.agent_loop.tool_dispatch import TOOL_REGISTRY
    
    # 获取意图对应的工具集
    tools = get_tools_for_intent(intent, TOOL_REGISTRY)
    
    if not tools:
        return ""
    
    lines = ["## 可用工具清单"]
    for t in tools:
        # 紧凑格式
        example = json.dumps(t.example_args, ensure_ascii=False)
        lines.append(f"  - {t.name}: {example}")
    
    return "\n".join(lines)
```

### 5.3 结果分层压缩（方案 C）

#### 5.3.1 修改文件

- `src/clude_code/tooling/feedback.py`

#### 5.3.2 增强实现

```python
# src/clude_code/tooling/feedback.py

# 添加压缩级别常量
COMPRESSION_SUMMARY = "summary"
COMPRESSION_COMPACT = "compact"
COMPRESSION_DETAILED = "detailed"

# 各工具的压缩配置
TOOL_COMPRESSION_CONFIG = {
    "grep": {
        "summary_fields": ["hits_total", "files_matched"],
        "compact_max_hits": 5,
        "compact_preview_len": 100,
        "detailed_max_hits": 20,
        "detailed_preview_len": 200,
    },
    "read_file": {
        "summary_fields": ["chars_total", "lines_total"],
        "compact_max_chars": 2000,
        "detailed_max_chars": 4000,
    },
    "list_dir": {
        "summary_fields": ["items_total", "dirs", "files"],
        "compact_max_items": 10,
        "detailed_max_items": 50,
    },
    "run_cmd": {
        "summary_fields": ["exit_code", "output_lines"],
        "compact_max_chars": 1000,
        "detailed_max_chars": 3000,
    },
}


def get_compression_level(
    tool: str,
    context_utilization: float,
    tool_call_count: int,
) -> str:
    """
    根据上下文使用率和工具调用次数决定压缩级别。
    
    规则：
    - 上下文 > 80%: 强制 summary
    - 首次调用: detailed
    - 重复调用 >= 2: summary
    - 其他: compact
    """
    if context_utilization > 0.8:
        return COMPRESSION_SUMMARY
    
    if tool_call_count == 0:
        return COMPRESSION_DETAILED
    
    if tool_call_count >= 2:
        return COMPRESSION_SUMMARY
    
    return COMPRESSION_COMPACT


def summarize_tool_result_v2(
    tool: str,
    tr: ToolResult,
    keywords: set[str] | None = None,
    compression_level: str = COMPRESSION_COMPACT,
) -> dict[str, Any]:
    """
    增强版工具结果摘要（支持分层压缩）。
    """
    if not tr.ok:
        return {"tool": tool, "ok": False, "error": tr.error}
    
    payload = tr.payload or {}
    config = TOOL_COMPRESSION_CONFIG.get(tool, {})
    
    if compression_level == COMPRESSION_SUMMARY:
        return _to_summary(tool, payload, config)
    elif compression_level == COMPRESSION_COMPACT:
        return _to_compact(tool, payload, config, keywords)
    else:
        return _to_detailed(tool, payload, config, keywords)


def _to_summary(tool: str, payload: dict, config: dict) -> dict:
    """仅返回统计摘要"""
    summary_fields = config.get("summary_fields", [])
    
    result = {"tool": tool, "ok": True, "level": "summary"}
    
    if tool == "grep":
        hits = payload.get("hits", [])
        files = set(h.get("path") for h in hits if isinstance(h, dict))
        result["stats"] = f"{len(hits)} hits in {len(files)} files"
    
    elif tool == "read_file":
        text = payload.get("text", "")
        result["stats"] = f"{len(text)} chars, {len(text.splitlines())} lines"
    
    elif tool == "list_dir":
        items = payload.get("items", [])
        result["stats"] = f"{len(items)} items"
    
    elif tool == "run_cmd":
        result["exit_code"] = payload.get("exit_code")
        out = payload.get("output", "")
        result["stats"] = f"{len(out.splitlines())} lines output"
    
    else:
        result["stats"] = "completed"
    
    result["has_more"] = True
    return result
```

---

## 6. 实施优先级

### 6.1 实施计划

| 阶段 | 方案 | 预期效果 | 工时 |
|------|------|---------|------|
| Phase 1 | A: 描述精简 | -600 tokens/请求 | 2h |
| Phase 2 | B: 动态工具集 | -1500~4000 tokens/请求 | 4h |
| Phase 3 | C: 结果分层压缩 | -500~2000 tokens/次调用 | 4h |
| Phase 4 | D+E+F: 优化增强 | -200~500 tokens | 2h |

### 6.2 预期总收益

| 场景 | 当前消耗 | 优化后 | 节省比例 |
|------|---------|--------|---------|
| 简单对话 | ~5000 tokens | ~1500 tokens | 70% |
| 代码分析 | ~8000 tokens | ~4000 tokens | 50% |
| 代码修改 | ~12000 tokens | ~6000 tokens | 50% |

### 6.3 风险评估

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 描述过简导致 LLM 误解 | 中 | 保留关键提示；回归测试 |
| 动态工具集遗漏必要工具 | 中 | 意图分类准确；兜底全量 |
| 压缩过度丢失关键信息 | 低 | 保留 has_more 标志；允许重查 |

---

## 7. 后续行动

1. **立即**: 实施方案 A（工具描述精简）
2. **本周**: 实施方案 B（动态工具集）
3. **下周**: 实施方案 C（结果分层压缩）
4. **持续**: 监控 Token 使用量，迭代优化

---

*文档版本: 1.0.0 | 最后更新: 2026-01-23*

