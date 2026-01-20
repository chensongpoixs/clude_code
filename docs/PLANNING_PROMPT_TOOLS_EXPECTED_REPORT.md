## 背景与目标

本次需求是：在 `AgentLoop._build_planning_prompt` 的 planning 提示词里，将 `tools_expected` 示例中的工具列表从“少量硬编码”升级为“包含当前工程全部现有工具”，并对相关代码做健壮性检查，最后把分析与改动写成汇报文件。

## 现状问题（Before）

- **`tools_expected` 硬编码且不全**：`AgentLoop._build_planning_prompt()` 示例里固定写了 `["read_file","grep","apply_patch"]`，导致模型在规划阶段容易忽略 `websearch/run_cmd/webfetch/...` 等已有工具。
- **工具清单存在单一事实来源**：工程里已经有稳定顺序的 `ToolSpec` 注册表（`tool_dispatch.iter_tool_specs()`），但 planning prompt 没有复用，存在“新增工具后忘记更新提示词”的风险。

## 实现方案（After）

### 1) tools_expected 自动覆盖“全部现有工具”

- **实现方式**：新增 `AgentLoop._get_prompt_tool_names()`，从 `tool_dispatch.iter_tool_specs()` 提取：
  - `visible_in_prompt == True`
  - `callable_by_model == True`
  的所有工具名，并保持注册表顺序。
- **落地位置**：在 `AgentLoop._build_planning_prompt()` 中，把 JSON 示例里的 `tools_expected` 替换为动态生成的完整工具数组（`json.dumps(..., ensure_ascii=False)`）。

### 2) 健壮性与降级策略

- **异常兜底**：若工具注册表导入/遍历异常，planning 阶段不会崩溃，自动回退到 `["read_file","grep","apply_patch"]`。
- **去重与过滤**：对工具名做空值过滤与去重，避免重复名导致提示混乱。
- **提示约束增强**：在 prompt 文本中增加“tools_expected 必须从工具名清单中选择”，减少模型胡乱编造工具名的概率。

## 额外发现与修复（Security & Hygiene）

### test_search.py 硬编码真实 API Key（高风险）

- 发现 `test_search.py` 内存在明文 `Serper` API Key，且直接 `print()` 输出响应内容。
- 已修复为：从环境变量读取 `SERPER_API_KEY` / `CLUDE_SEARCH__SERPER_API_KEY`，并只打印结果摘要（标题+链接），避免敏感信息泄露与控制台刷屏。

## 关键改动文件

- `src/clude_code/orchestrator/agent_loop/agent_loop.py`
  - 新增 `_get_prompt_tool_names()`
  - `_build_planning_prompt()` 的 `tools_expected` 示例改为“全量工具名”
- `test_search.py`
  - 移除硬编码 key；改为 env 注入；输出降噪

## 风险与后续建议

- `agent_loop.py` 仍存在多处“函数体内 Docstring”的历史遗留，严格按现行代码规范需要逐步迁移为“声明前注释块”。本次变更只对新改动的 planning prompt 相关方法做了规范化处理，未做全文件重构以避免风险扩散。


