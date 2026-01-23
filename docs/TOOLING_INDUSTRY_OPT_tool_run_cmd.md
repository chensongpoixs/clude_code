## run_cmd（`src/clude_code/tooling/tools/run_cmd.py`）业界优化点

### 当前模块职责

- 在工作区内执行命令，做基础环境脱敏、超时控制与输出上限治理。

### 业界技术原理

- **默认 shell=False**：绝大多数“只想运行一个程序 + 参数”的场景不需要 shell，shell 会引入注入风险与平台差异。
- **显式 shell 特性检测**：当命令包含管道/重定向/连接符等 shell 语义时才启用 shell=True。
- **输出上限与头尾截断**：保留关键报错与最终结果（尾部更重要），同时保留头部环境信息，避免仅 tail 丢上下文。
- **最小环境（env scrub）**：避免把 API Key/Token/代理等敏感环境变量泄露给子进程或日志。

### 现状评估（本项目）

- 已实现：`_parse_command()` 做 shell 特性检测；尽量走 shell=False。
- 已实现：`_truncate_output()` 头尾截断。
- 已实现：timeout + env scrub。
- 另有更上层的 `policy/command_policy.py` 用于策略判定（建议由 tool_lifecycle/风险路由统一调用）。

### 可优化点（建议优先级）

- **P0：更稳健的 Windows 命令解析**
  - **原理**：Windows 的命令行解析与 Unix 不同，简单 split 容易误拆引号/转义。
  - **建议**：优先支持“明确数组参数”的协议（args: list[str]），把字符串命令当作兼容模式；或在 Windows 使用更严格的解析策略。

- **P1：资源限制与工作目录沙箱**
  - **原理**：命令可能产生大量输出/占满磁盘/长时间占用 CPU。
  - **建议**：引入 `max_runtime_s`、`max_output_bytes`、可选 `allow_network` 等参数，并在 policy 层强制。

- **P2：流式输出（stream stdout）**
  - **原理**：长命令只截断最终输出会丢进度信息；流式输出也能更快停机。
  - **建议**：用 `Popen` 流式读取 stdout/stderr，并在达到 budget 时终止进程。


