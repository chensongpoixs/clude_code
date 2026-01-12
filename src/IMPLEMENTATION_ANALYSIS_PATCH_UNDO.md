# Patch/Undo 工程化落地：实现分析流程（含边界与风险）

本文件用于解释本仓库中 `apply_patch / undo_patch` 的实现思路、关键难点与工程权衡，并给出“为什么这么做”的可审计依据。

---

## 1. 目标与非目标

### 1.1 目标
- **Patch-first**：默认以“最小变更块”修改文件，而非整文件重写
- **可回滚**：每次 patch 都能生成可用的回滚点（undo_id）
- **可追溯**：审计日志记录 before/after hash（可证明发生了什么）
- **安全防误改**：多处匹配时必须显式声明期望替换次数

### 1.2 非目标（当前版本不做）
- AST 级编辑（语法树修改）
- 三方 merge 工具级冲突解决（仅做最小 hash 冲突保护）
- 全量回放/评测系统（后续 v1）

---

## 2. 设计原则（对标业界 Aider/Cursor/Claude Code）

- **唯一性保护**：避免“旧代码块”匹配到多个位置导致大范围误改（这是业界最常见事故）
- **失败优先**：不确定就失败，要求更明确的 `old` 上下文；不做模棱两可的修改
- **证据链**：用 `sha256(before)` 与 `sha256(after)` 做最小审计证据

---

## 3. apply_patch 的实现流程（逐步）

实现位置：`src/clude_code/tooling/local_tools.py::apply_patch`

### 3.1 输入参数
- `path`: 目标文件（强制 workspace 内）
- `old`: 旧代码块（建议包含前后 3~10 行上下文）
- `new`: 新代码块
- `expected_replacements`:
  - `>0`：必须精确匹配该次数，否则失败
  - `==0`：替换所有匹配
- `fuzzy`: 是否启用模糊匹配（默认 false）
- `min_similarity`: 模糊匹配阈值（默认 0.92）

### 3.2 主流程
1. **路径沙箱**：`_resolve_in_workspace()` 防止 `..` 越权
2. **读取内容**：得到 `before_text`
3. **计算 before_hash**：`sha256(before_text)`
4. **匹配模式选择**：
   - **exact**：`old in before_text`
     - 统计 occurrences
     - 校验 `expected_replacements`（唯一性保护）
     - 执行 replace（N 次或全量）
   - **fuzzy**：`old not in before_text` 且 `fuzzy=True`
     - 仅支持 `expected_replacements=1`
     - 采用“anchor + 行窗口”的候选搜索：
       - 从 `old` 中取最长非空行作为 anchor，缩小候选窗口
       - 用 `SequenceMatcher` 计算相似度，选 best
       - best < threshold 则失败
5. **生成 undo 备份**：
   - 写入 `.clude/undo/{undo_id}.bak`（保存整个 before_text）
   - 写入 `.clude/undo/{undo_id}.json`（记录 path、before_hash、after_hash、replacements、mode）
6. **写入更新内容**：覆盖写入 `updated_text`
7. **返回 payload**：包含 `undo_id`、`before_hash`、`after_hash`、模式与替换次数

### 3.3 为什么要保存“整文件备份”
- 对于 MVP，整文件备份最稳：即使后续 `new` 又被改动，仍可准确回滚
- 代价：空间占用（后续可改为 delta/压缩/保留策略）

---

## 4. undo_patch 的实现流程（逐步）

实现位置：`src/clude_code/tooling/local_tools.py::undo_patch`

### 4.1 输入参数
- `undo_id`
- `force`（默认 false）

### 4.2 主流程
1. 读取 `.clude/undo/{undo_id}.json` 找到：
   - `path`
   - `after_hash`（用于冲突检测）
   - `backup_file`（.bak）
2. **冲突检测**（默认开启）：
   - 计算当前文件 `current_hash`
   - 若 `current_hash != recorded after_hash` 且 `force=False` → 拒绝回滚（避免覆盖其他新改动）
3. 读取 `.bak` 得到 `before_text` 并写回文件
4. 返回 payload（含 hash 与冲突前 hash）

---

## 5. 审计日志（before/after hash 的证据链）

实现位置：`src/clude_code/orchestrator/agent_loop.py`

- `tool_call` 事件对 `apply_patch/undo_patch` 会额外记录 `payload`：
  - `undo_id`
  - `before_hash` / `after_hash`（或 restore hash）
  - `mode` / `replacements`

这让我们在不保存巨量 diff 的情况下，也能证明“某次工具调用确实改变了文件内容”。

---

## 6. 风险与后续改进

- **原子写**：当前 patch/undo 仍是直接 write_text（下一步升级为 temp + rename）
- **敏感信息**：审计日志未来需脱敏（避免把密钥写入 data）
- **模糊匹配风险**：fuzzy 只能用于单次替换且有阈值；后续可升级为 AST/LSP 定位


