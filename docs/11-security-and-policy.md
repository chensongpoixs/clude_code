# 11｜安全与策略（Security & Policy）

目标：让 agent 在本地拥有强能力的同时，仍然满足“最小权限、默认安全、可审计、可解释拒绝”。

## 1. 威胁模型（必须先写清）

### 1.1 主要风险
- **越权访问**：读取 workspace 外文件、读取凭据目录、扫描磁盘
- **越权执行**：执行破坏性命令、植入后门、开启网络外联
- **数据泄露**：把敏感信息写入日志/上下文/提交到 git
- **供应链风险**：自动安装依赖、运行未知脚本

### 1.2 安全边界（默认）
- 只能访问 workspace（含其子目录）
- 默认禁用网络
- 默认禁止 push、禁止重写历史
- 默认过滤敏感环境变量

## 2. 策略引擎（Policy Engine）

### 2.1 输入/输出
- 输入：ToolCallRequest、用户配置、workspace 元数据（路径、ignore、敏感目录规则）
- 输出：ALLOW / DENY / REQUIRE_CONFIRMATION

### 2.2 规则表达（建议）
- 基于声明式规则（YAML/JSON）+ 少量代码扩展
- 规则维度：
  - tool name/version
  - path（glob/regex）
  - command（regex/allowlist）
  - risk score（组合评估）

### 2.3 确认机制（Confirmation）
- scope：
  - `single_action`：本次一次性
  - `session`：本会话内有效
  - `workspace`：对当前仓库长期有效（写入配置，需更强确认）
- 任何确认都必须写入审计日志

### 2.4 工具级权限（对标 Claude Code 的 allowedTools/disallowedTools）
- **目标**：在“写/执行确认”之外，再增加一层**工具级 allow/deny**，避免模型误用不该使用的工具。
- **建议实现**：
  - `policy.allowed_tools`：允许名单（空=不限制）
  - `policy.disallowed_tools`：禁止名单
- **拦截点**：在工具生命周期入口（如 `tool_lifecycle.py`）最前面拦截，并写入 `audit.jsonl`（event=`policy_deny_tool`）。

## 3. 路径与文件策略

### 3.1 禁止目录（默认建议）
- `.ssh/`, `.gnupg/`
- 系统用户目录下的浏览器配置/凭据目录
- `.git/objects`（通常不需要）

### 3.2 写入限制
- 禁止写入二进制（默认）
- 大文件写入需要确认
- 对 `package-lock.json`、`pnpm-lock.yaml` 这种自动生成文件：允许但需提示“可能造成大 diff”

## 4. 命令执行策略

### 4.1 命令 allowlist
- 从项目配置推断（例如 `package.json` scripts）
- 允许：lint/test/build/format 等
- 禁止：下载执行、系统管理、磁盘破坏

### 4.2 运行脚本风险
- `npm postinstall` 等生命周期脚本可触发网络与任意执行
- 建议默认策略：
  - 安装依赖需要确认
  - 提示用户在隔离环境执行

## 5. 敏感信息防护（必做）

### 5.1 检测
- 正则 + 熵检测 + 关键字：
  - `AKIA...`（AWS）
  - `-----BEGIN PRIVATE KEY-----`
  - `Bearer ` token
- 对模型输出与工具输出都做扫描

### 5.2 处置
- 日志脱敏（mask）
- 阻断写入（如果检测到将密钥写进文件/提交信息）
- 提示用户用环境变量/secret manager

## 6. 审计（Audit）

### 6.1 必须记录
- 每次工具调用（参数脱敏后）、结果、耗时、影响文件
- 每次确认（谁确认、确认了什么范围）
- 每次写文件（old/new hash、patch）

### 6.2 访问与保留
- 默认保留 7~30 天（可配置）
- 企业版：集中式存储 + 只读访问 + 签名防篡改


