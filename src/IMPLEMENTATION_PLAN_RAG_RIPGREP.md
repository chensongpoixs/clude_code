# 结构化工具回喂 + Ripgrep（rg）落地方案：业界同等稳健的实现规划

本文回答两个问题：
1) 业界（Aider/Cursor/Claude Code）为什么更稳？  
2) 在本项目规划中，如何用“结构化回喂 + rg”把稳定性补齐？（含详细分析流程）

---

## 1. 问题定义（你遇到的现象背后）

### 1.1 为什么“整段 payload 回喂”会不稳
- **上下文膨胀**：工具输出（目录列表、grep 命中、命令 stdout）容易一次就几千/几万字符，导致后续回合：
  - 模型抓不到关键信息 → 误判
  - 触发服务端模板/上下文限制（不同后端表现不同）
- **信息噪声**：模型真正需要的是“下一步决策所需的最小证据”，而不是全量输出。
- **错误定位弱**：工具输出大段文本时，你很难在 trace 里快速看清关键字段，排障成本高。

### 1.2 为什么 Python rglob grep 会不稳
- **性能不可预测**：大仓库/多小文件时，Python 遍历 + 逐文件读文本会变慢、并且容易把非文本/大文件拖垮。
- **结果格式不标准**：rg 有稳定的输出格式、上下文控制、glob、大小写、多行等能力，便于结构化解析。

---

## 2. 业界如何做（抽象成可实现机制）

### 2.1 Aider：稳定来自“精确编辑 + 精简上下文”
- 编辑协议偏向 patch/search-replace（我们已在 patch 方向补齐）
- 输出回喂时倾向传 **diff/关键片段**，而不是整段日志

### 2.2 Cursor：稳定来自“索引/RAG + IDE 可视化”
- 不把仓库整体塞进上下文；通过索引检索只注入最相关片段
- UI 层展示 diff、引用、调用链，降低误操作

### 2.3 Claude Code：稳定来自“工具驱动 + 可验证闭环”
- 依赖 bash/grep 等工具探索，但会尽量把工具结果总结成下一步证据

---

## 3. 本项目的落地目标（可验收）

### 3.1 结构化回喂（Tool Feedback Summarization）

**目标**：模型收到的工具结果永远是“小而准”的结构化摘要，并在需要时提供“可追溯引用”（文件/行号/片段）。

**验收标准**（建议）：
- 任意工具回喂 `content` 长度控制在阈值内（例如 2~4KB）；
- grep/search 回喂必须包含：
  - `hits_total`、`hits_shown`
  - topN 命中：`path`、`line`、`preview`
  - 若有截断：`truncated=true`
- run_cmd 回喂必须包含：
  - `exit_code`
  - `error_tail`（末尾 N 行）
  - `summary`（一句话）

### 3.2 用 rg 替换 rglob grep（Deterministic Search）

**目标**：将搜索从“Python 遍历”升级到“rg 一等公民”。

**验收标准**：
- `rg` 存在时优先使用；缺失时自动降级到 Python grep（但提示）
- 结果结构化：文件、行号、preview、（可选）上下文
- 支持常用参数：`-i`、glob、head_limit、scope path

---

## 4. 详细分析流程（如何从问题到方案）

这部分是你要的“分析思考流程”，按工程落地的标准步骤写：

### 4.1 采样问题与证据
- 收集 `trace.jsonl`：
  - 找出“工具回喂长度过大”的回合
  - 统计每类工具 payload 的平均/95 分位长度
- 收集失败样例：
  - 模型误判
  - 后端报错（模板/上下文）
  - 搜索过慢或卡死

### 4.2 建模（把问题拆成可优化的变量）
- 变量 A：回喂长度（bytes/chars）
- 变量 B：信息密度（关键字段占比）
- 变量 C：检索耗时（ms）
- 变量 D：命中质量（topN 是否命中正确文件）

### 4.3 方案设计（结构化摘要的协议）
为每个 tool 定义“回喂摘要 schema”（不是 tool 返回 schema，而是**喂给模型**的 schema）：
- `list_dir`：只给 topN 名称 + 统计（items_total，dirs/files）
- `grep/rg`：只给 topN 命中 + hits_total + truncated
- `read_file`：只给片段范围 + content（限制行数/字节）
- `run_cmd`：只给 exit_code + tail + 关键报错定位
- `apply_patch/undo_patch`：只给 undo_id + before/after hash + replacements

### 4.4 风险评估（为什么不会“过度压缩”）
- 若摘要不足：允许模型请求“扩展片段”（例如 `read_file` 指定范围）
- 保留“可追溯引用”：path+行号+snippet_id
- 保留“错误尾部”：编译/测试错误通常在末尾

### 4.5 迭代计划（最小可行 → 稳健）
- v0（1 天）：实现 tool feedback summarizer（统一入口），先做 grep/list_dir/run_cmd
- v1（1~2 天）：接入 rg（可选安装检查 + 降级）
- v2（2~3 天）：引入“上下文预算器”（按字节/token 估算裁剪）

---

## 5. 代码落地位置建议（对齐本仓库结构）

- `src/clude_code/tooling/feedback.py`：ToolResult → FeedbackSummary（新）
- `src/clude_code/tooling/local_tools.py`：grep 改为调用 rg（优先）或 fallback
- `src/clude_code/orchestrator/agent_loop.py`：回喂统一走 feedback summary（替代直接 json dump payload）
- `src/clude_code/cli/main.py`：`doctor` 增加 rg 检查（可选）


