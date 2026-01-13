# 企业策略下发系统

> 模块路径: `src/clude_code/policy/`
> 阶段: Phase 4 - 生态与扩展

---

## 概述

本模块提供企业级策略管理能力，支持远程策略下发、RBAC 权限控制、合规审计等功能。

## 业界对比

| 项目 | 企业策略 | RBAC | 远程下发 | 审计集成 |
|:---|:---|:---|:---|:---|
| **GitHub Copilot Enterprise** | ✅ | ✅ | ✅ | ✅ |
| **Cursor Enterprise** | ✅ | 部分 | ✅ | ✅ |
| **Claude for Enterprise** | ✅ | ✅ | ✅ | ✅ |
| **本项目** | ✅ | ✅ | ✅ | ✅ |

## 核心功能

### 1. RBAC 权限模型

```
┌─────────────────────────────────────────────────────────┐
│                    Permission                           │
│  ┌─────────────┬─────────────┬─────────────────────┐   │
│  │ file:read   │ cmd:exec    │ tool:plugin         │   │
│  │ file:write  │ cmd:network │ tool:lsp            │   │
│  │ file:delete │ cmd:sudo    │ tool:semantic       │   │
│  └─────────────┴─────────────┴─────────────────────┘   │
│                         │                               │
│                   ┌─────┴─────┐                         │
│                   ▼           ▼                         │
│             ┌─────────┐ ┌─────────┐                    │
│             │  Role   │ │  Role   │                    │
│             │ (admin) │ │(developer)│                   │
│             └────┬────┘ └────┬────┘                    │
│                  │           │                          │
│                  └─────┬─────┘                          │
│                        ▼                                │
│                  ┌──────────┐                           │
│                  │   User   │                           │
│                  └──────────┘                           │
└─────────────────────────────────────────────────────────┘
```

### 2. 预定义角色

| 角色 | 权限 | 说明 |
|:---|:---|:---|
| `admin` | 全部 | 管理员 |
| `developer` | file:read/write, cmd:exec, tool:* | 开发者 |
| `reviewer` | file:read, sys:audit_view | 代码审查者 |
| `guest` | file:read | 访客 |

### 3. 策略加载优先级

```
远程服务器 → 本地缓存 → 本地配置文件 → 默认策略
```

## 配置示例

### 策略文件 (.clude/policy.yaml)

```yaml
version: "1.0.0"
organization: "My Company"

# 自定义角色
roles:
  senior_dev:
    name: senior_dev
    description: "高级开发者"
    permissions:
      - file:read
      - file:write
      - cmd:exec
      - cmd:network
      - tool:plugin

# 用户配置
users:
  alice:
    id: alice
    name: "Alice"
    roles: ["senior_dev"]
    extra_permissions: ["sys:audit_view"]
  
  bob:
    id: bob
    name: "Bob"
    roles: ["developer"]
    denied_permissions: ["cmd:network"]

default_role: developer

# 路径规则
path_rules:
  - pattern: "**/.env*"
    allow: false
    permissions: ["file:read", "file:write"]
  - pattern: "**/secrets/**"
    allow: false

# 命令规则
command_denylist:
  - "rm -rf"
  - ":(){ :|:& };:"
  - "sudo rm"

command_allowlist: []  # 空表示不限制

# 全局开关
allow_network: false
allow_sudo: false
require_confirmation: true

# 审计配置
audit_enabled: true
audit_retention_days: 90

# 插件控制
blocked_plugins: ["dangerous_plugin"]
allowed_plugins: []  # 空表示允许所有
```

### 远程策略服务器

```python
# 配置远程策略 URL
engine = PolicyEngine(
    workspace_root,
    policy_server_url="https://policy.mycompany.com/api/v1/policy",
    cache_ttl_s=3600,
)
```

## 使用示例

### 检查权限

```python
from clude_code.policy.enterprise_policy import PolicyEngine, Permission

engine = PolicyEngine(workspace_root)
engine.set_current_user("alice")

# 检查文件访问
decision = engine.check_file_access("src/main.py", "write")
if not decision.allowed:
    print(f"拒绝: {decision.reason}")

# 检查命令执行
decision = engine.check_command("npm install")
if decision.allowed:
    subprocess.run(["npm", "install"])
```

### 检查插件

```python
decision = engine.check_plugin("my_plugin")
if decision.allowed:
    result = plugin_registry.execute("my_plugin", args)
```

### 获取策略摘要

```python
summary = engine.get_policy_summary()
# {
#     "version": "1.0.0",
#     "organization": "My Company",
#     "current_user": "alice",
#     "current_permissions": ["file:read", "file:write", ...],
#     ...
# }
```

## 健壮性设计

### 1. 策略缓存

- 远程拉取失败时降级到缓存
- 缓存过期后自动刷新
- 支持离线工作

### 2. 安全默认值

- 默认禁止网络访问
- 默认禁止 sudo
- 默认需要写操作确认

### 3. 审计集成

```python
# 所有策略决策都会记录到审计日志
audit.write(
    trace_id=trace_id,
    event="policy_decision",
    data={
        "action": "file_write",
        "path": "src/main.py",
        "allowed": True,
        "user": "alice",
    },
)
```

## 企业部署

### 1. 策略服务器

企业可部署策略服务器，统一管理所有客户端的策略：

```
┌──────────────────────────────────────────────────┐
│                 Policy Server                    │
│  ┌────────────────────────────────────────────┐  │
│  │ - 策略版本管理                              │  │
│  │ - 用户/角色管理                             │  │
│  │ - 审计日志收集                              │  │
│  │ - 合规报告                                  │  │
│  └────────────────────────────────────────────┘  │
│                        │                         │
│          ┌─────────────┼─────────────┐          │
│          ▼             ▼             ▼          │
│     ┌─────────┐  ┌─────────┐  ┌─────────┐      │
│     │ Client  │  │ Client  │  │ Client  │      │
│     └─────────┘  └─────────┘  └─────────┘      │
└──────────────────────────────────────────────────┘
```

### 2. 配置分发

```bash
# 设置策略服务器 URL
export CLUDE_POLICY_SERVER="https://policy.example.com"

# 或在配置文件中指定
# .clude/config.yaml
policy:
  server_url: "https://policy.example.com"
  cache_ttl_s: 3600
```

