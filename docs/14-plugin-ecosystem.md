# 14｜插件与工具生态（Plugin Ecosystem）

目标：允许第三方/团队扩展工具与能力，同时不破坏安全与兼容性。

## 1. 插件模型

### 1.1 两类扩展
- **工具插件（Tool Plugin）**：新增 tool（例如 Jira、K8s、内部 API）
- **策略插件（Policy Plugin）**：新增/覆盖策略规则（企业合规）

### 1.2 CLI 命令扩展（对标 Claude Code 的 commands）
- **自定义命令（项目级）**：`.clude/commands/*.md`
  - **用途**：把常用 prompt/流程沉淀成可复用命令（例如 `/review <path>`、`/release-notes`）
  - **行为**：命令只做 prompt 模板展开，执行仍走 AgentLoop（受 ToolSpec/Policy/Confirm/Audit 约束）
  - **能力**：
    - 参数校验：`args/required/usage`
    - 命令级权限声明：`allowed_tools/disallowed_tools/allow_network`（仅本次执行生效）

### 1.2 插件包结构（建议）
- `manifest.json`
  - `name`, `version`
  - `tools[]`（每个 tool 的 schema 与权限声明）
  - `entrypoint`（可执行/脚本）
  - `min_host_version`
  - `capabilities`（fs/proc/net）

## 2. 工具注册与隔离

### 2.1 注册流程
- 启动时加载 manifest
- 校验签名/来源（企业版）
- 将 tools 注入 Tool Registry

### 2.2 隔离原则
- 插件只能通过 Host 提供的受控 API 执行
- 插件进程与 host 分离（子进程/容器）
- 插件工具同样受 Policy Engine 约束

## 3. 版本与兼容
- host 与插件都采用 semver
- host 升级必须保证：
  - 旧插件至少能被“明确拒绝并提示原因”
  - schema 变更需要 MAJOR bump

## 4. MVP 实现建议
- 先做：内置工具 registry + schema 校验
- 再做：外部工具以“子进程协议”接入
- 最后做：签名、权限细分、企业分发渠道


