# 15｜部署与运维（Local / Enterprise）

目标：让该类 code agent 能在个人本地与企业内网稳定运行，并可配置、可升级、可治理。

## 1. 运行形态

### 1.1 本地版（个人）
- CLI 二进制/脚本
- 索引与记忆保存在 workspace 或用户目录
- 默认禁网、默认最小权限

### 1.2 企业版（内网）
- 模型：私有化模型服务或代理网关
- 审计：集中式日志/回放存储
- 策略：组织级策略下发（policy bundle）
- 插件：内部工具接入（Jira/GitLab/监控）

## 2. 配置体系（建议）

### 2.1 配置来源优先级
1. 命令行参数
2. workspace 配置（例如 `.clude/config.json`）
3. 用户全局配置（用户目录）
4. 默认值

### 2.2 配置项示例
- `network.enabled: boolean`
- `network.allowlist: string[]`
- `verify.default_mode: lint|test|build`
- `tools.enable_semantic_search: boolean`
- `limits.max_files_changed: number`
- `audit.retention_days: number`

## 3. 更新与版本管理
- 本地：自更新（可选）或包管理器更新
- 企业：灰度发布、版本锁定、回滚包

## 4. 运维与故障处理
- 提供 `doctor` 命令：
  - 检查依赖（rg/git/node/python）
  - 检查权限与策略
  - 检查索引健康度
- 提供导出诊断包：
  - trace + 关键日志 + 配置（脱敏）


