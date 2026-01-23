# Phase 2: 动态工具集 - 实现思考过程

> **开始时间**: 2026-01-23  
> **目标**: 根据意图动态加载工具集，预期节省 1500-4000 tokens/请求

---

## 1. 问题分析

### 1.1 当前状态

- 所有 23 个工具在每次请求都注入 System Prompt
- 用户仅询问"你好"时也加载 grep、apply_patch 等工具
- 大量工具与当前任务无关，浪费 token

### 1.2 业界做法

| 项目 | 策略 |
|------|------|
| Claude Code | 根据任务类型动态加载工具集 |
| Cursor | 先给核心工具，需要时再扩展 |
| OpenAI | 建议每请求 ≤10 个工具 |

### 1.3 目标

根据意图分类结果，动态选择工具集：

| 意图 | 需要的工具 | 工具数 |
|------|-----------|--------|
| GENERAL_CHAT | display | 1 |
| CODE_ANALYSIS | list_dir, read_file, grep, glob_file_search, search_semantic | 5 |
| CODE_MODIFICATION | 上述 + apply_patch, write_file, undo_patch | 8 |
| CODE_EXECUTION | 上述 + run_cmd | 9 |
| WEB_RESEARCH | readonly + webfetch, websearch, codesearch | 8 |

---

## 2. 设计方案

### 2.1 工具分组

```python
TOOL_GROUPS = {
    "minimal": ["display"],
    "readonly": ["list_dir", "read_file", "grep", "glob_file_search", "search_semantic"],
    "write": ["apply_patch", "write_file", "undo_patch"],
    "exec": ["run_cmd"],
    "web": ["webfetch", "websearch", "codesearch"],
    "task": ["todowrite", "todoread", "run_task", "get_task_status"],
    "utility": ["question", "load_skill", "get_weather", "get_weather_forecast", "preview_multi_edit"],
}
```

### 2.2 意图到工具集映射

```python
INTENT_TO_GROUPS = {
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
    "UNKNOWN": ["readonly", "write", "exec"],  # 兜底
}
```

### 2.3 集成点

1. **新增模块**: `src/clude_code/tooling/tool_groups.py`
2. **修改 AgentLoop**: 在 `_build_system_prompt()` 中使用动态工具集
3. **修改 tool_dispatch**: 添加 `get_tools_for_intent()` 函数

---

## 3. 实现步骤

### 3.1 创建 tool_groups.py

定义工具分组和意图映射。

### 3.2 修改 tool_dispatch.py

添加 `get_tools_for_intent()` 函数，根据意图返回工具集。

### 3.3 修改 AgentLoop

在构建系统提示时，根据当前意图选择工具集。

---

## 4. 风险评估

| 风险 | 缓解措施 |
|------|---------|
| 遗漏必要工具 | 兜底 UNKNOWN 包含常用工具 |
| 意图分类错误 | 允许 LLM 请求额外工具 |
| 复杂任务需要多种工具 | 提供 "expand_tools" 命令 |

---

## 5. 实现进度

| 步骤 | 状态 |
|------|------|
| 思考过程文档 | ✅ 已完成 |
| 创建 tool_groups.py | ✅ 已完成 |
| 修改 tool_dispatch.py | ✅ 已完成 |
| 修改 AgentLoop | ✅ 已完成 |
| 代码检查 | ✅ 已通过 |
| 汇报 | ✅ 已完成 |

---

## 6. 完成汇报

### 6.1 创建的文件

- `src/clude_code/tooling/tool_groups.py` - 工具分组与动态加载模块

### 6.2 修改的文件

- `src/clude_code/orchestrator/agent_loop/tool_dispatch.py` - 添加 `render_tools_for_intent()` 函数
- `src/clude_code/orchestrator/agent_loop/agent_loop.py` - 集成动态工具集更新逻辑

### 6.3 Token 节省测算

| 意图 | 工具数 | 全量对比 | 节省 tokens |
|------|--------|---------|------------|
| GENERAL_CHAT | 1 | 23 → 1 | **~403** |
| CAPABILITY_INQUIRY | 1 | 23 → 1 | **~403** |
| CODE_ANALYSIS | 5 | 23 → 5 | **~330** |
| CODE_MODIFICATION | 9 | 23 → 9 | **~250** |
| CODE_EXECUTION | 10 | 23 → 10 | **~230** |

### 6.4 验证结果

```
全量工具: ~417 tokens
GENERAL_CHAT 工具: ~14 tokens
节省: ~403 tokens (96.6%!)
```

### 6.5 集成点

1. **意图识别后自动更新**: `_classify_intent_and_decide_planning()` 调用 `_update_tools_for_intent()`
2. **System Prompt 动态构建**: `_build_system_prompt_from_profile()` 使用更新后的 `_tools_section`
3. **兜底机制**: UNKNOWN 意图使用 readonly + write + exec 组

