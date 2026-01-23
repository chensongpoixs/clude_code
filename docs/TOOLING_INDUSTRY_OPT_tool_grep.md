## grep（`src/clude_code/tooling/tools/grep.py`）业界优化点

### 当前模块职责

- 在工作区内按正则搜索文本内容：优先使用 `rg`（ripgrep），不可用时回退 Python 扫描。
- 输出面向 agent：以较低 token 成本提供可定位的命中（path/line/preview）。

### 业界技术原理

- **“机器可用”与“模型可用”的输出格式选择**：  
  - `rg --json` 信息更全，但冗余字段多、token 重。  
  - `rg --vimgrep` 信息密度高（file:line:col:text），非常适合 LLM 快速定位与后续 read_file 二次读取。
- **早停（early stop）**：达到 `max_hits` 后应立即停止搜索进程，避免在大仓库里无意义地继续扫描。
- **文件过滤优先（减少扫描面）**：通过语言后缀、include_glob、忽略目录等“缩小候选集合”，比事后截断更省。

### 现状评估（本项目）

- 已实现：rg 优先 + Python fallback；并强调 `--vimgrep` 的 token 经济性（见模块注释）。
- 已实现：language→后缀映射、忽略目录、max_hits 上限控制（实际实现以 `_rg_grep/_python_grep` 为准）。
- 已在回喂层 `tooling/feedback.py` 做了 hits 数量截断与 preview 截断。

### 可优化点（建议优先级）

- **P0：稳定的命中结构（统一字段）**
  - **原理**：grep 的返回字段会被后续工具链（read_file/patching）依赖。
  - **建议**：统一输出：`pattern/path/engine/hits_total/hits_shown/truncated/hits[]`，hits 固定包含 `path/line/col/preview`。

- **P1：更强的二次定位（match_id）**
  - **原理**：让后续“读取/编辑”能引用同一个命中，减少歧义。
  - **建议**：每个 hit 计算 `match_id=f\"{path}:{line}:{col}\"`。

- **P1：更精细的 ignore（尊重 .gitignore/.cludeignore）**
  - **原理**：业界普遍默认尊重仓库忽略规则，降低噪音与隐私风险。
  - **建议**：rg 已可天然读取 .gitignore；Python fallback 可加载一份 ignore 规则并复用到 glob/遍历中。


