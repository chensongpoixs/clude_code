# 07｜运行时与命令执行（Runtime & Terminal）

目标：以“可控且可审计”的方式执行构建/测试/脚本，并管理输出与后台任务。

## 1. 子模块拆分

### 1.1 Command Runner
- **职责**：执行命令、捕获输出、超时控制、返回结构化结果
- **输入**：`command`, `cwd`, `env`, `timeout_ms`, `is_background`
- **输出**：
  - `exit_code`
  - `stdout/stderr`（裁剪后）
  - `duration_ms`
  - `pid`（后台）

### 1.2 Output Manager
- **职责**：输出裁剪、去噪、摘要（面向上下文注入）
- **策略**：
  - 统一最大输出字节数
  - 保留“错误尾部”更重要（常见编译错误在末尾）
  - 识别常见噪声（进度条、重复行）做折叠

### 1.3 Background Job Manager（可选）
- **职责**：跟踪后台任务生命周期
- **接口**：
  - `jobs.list`
  - `jobs.stop(job_id)`
  - `jobs.logs(job_id, tail_n)`

## 2. 安全策略（强制）

### 2.1 命令准入
- 默认 deny 网络相关工具（curl/wget/Invoke-WebRequest）
- 禁止破坏性命令（rm -rf、format disk）
- 允许的构建/测试命令从仓库配置中生成 allowlist（例如 package.json scripts）

### 2.2 环境变量保护
- 默认不向子进程注入敏感变量（`*_TOKEN`, `*_KEY`, `AWS_*` 等）
- 允许通过显式配置放行

## 3. 结果结构化（便于 agent 推理）

建议对常见输出做解析：
- 测试：失败用例列表、失败堆栈位置、重试建议
- 构建：错误文件、行号、错误码
- lint：规则名、位置、自动修复建议

## 4. MVP 实现建议
- 先做：同步执行 + 超时 + 输出裁剪
- 再做：后台任务管理
- 最后做：输出结构化解析与可视化


