# 三项稳健性增强：feedback 摘要回喂 + rg 搜索 + doctor 检查（分析流程与实现思路）

对应你的三项需求：
1) `tooling/feedback.py`：ToolResult → 结构化摘要回喂  
2) `local_tools.grep()`：优先 `rg --json`，保留 fallback  
3) `doctor`：检测 rg 并提示安装

---

## 1) 分析流程（从问题到落地）

### 1.1 采样问题
- 观察失败样例：上下文膨胀、模型误判、后端模板限制、搜索慢/卡死
- 从 `.clude/logs/trace.jsonl` 统计：
  - 工具回喂平均/95 分位长度
  - grep 命中数、执行时间（后续可加）

### 1.2 归因建模
- **回喂不稳**：payload 大 + 噪声高 → 模型难以抓住决策信号
- **搜索不稳**：Python rglob 性能不可预测 → 大仓库变慢
- **环境不稳**：不同机器是否装了 rg 不一致 → 行为差异

### 1.3 设计原则（对标业界）
- 回喂只给“决策关键字段 + 可追溯引用（path/line/preview）”
- 搜索用 rg 获取“标准化、可结构化”的结果
- doctor 提前暴露环境差异，减少“跑不起来”的排障成本

---

## 2) 实现思路（工程化细节）

### 2.1 结构化回喂（`src/clude_code/tooling/feedback.py`）

关键点：
- 不再把 `ToolResult.payload` 原样 json dump 回喂模型
- 针对不同 tool 输出不同摘要 schema：
  - `list_dir`: items_total/dirs/files + topN items
  - `grep`: engine/hits_total/hits_shown + topN hits(path/line/preview)
  - `run_cmd`: exit_code + output_tail（末尾 N 行，保留错误信息）
  - `apply_patch/undo_patch`: undo_id + before/after hash

### 2.2 rg 搜索（`src/clude_code/tooling/local_tools.py`）

实现策略：
- `shutil.which("rg")` 存在则走 `_rg_grep`
- `_rg_grep` 调 `rg --json` 并解析 `type=match` 事件
- 若 rg 不可用/执行失败，则降级 `_python_grep`

### 2.3 doctor 检测（`src/clude_code/cli/main.py`）

实现策略：
- `doctor` 输出 `ripgrep (rg): <path or NOT FOUND>`
- 未安装时给出 conda/choco/scoop 的安装提示

---

## 3) 验收标准（建议）
- 在大仓库中 grep 明显提速（rg）
- trace 中 tool feedback 长度显著下降（结构化摘要）
- 新机器跑 `doctor` 能快速定位“缺 rg”问题


