# Tool 插件系统

> 模块路径: `src/clude_code/plugins/`
> 阶段: Phase 4 - 生态与扩展

---

## 概述

本模块提供可扩展的工具插件系统，支持用户通过 YAML/JSON 配置文件注册自定义工具，并在沙箱环境中安全执行。

## 补充：UI 插件（实验性，P0-2）

为避免 `cli/` 主链路膨胀，本项目把“增强 Live UI/实验交互实现”以**内置插件形态**收纳在：
- `src/clude_code/plugins/ui/`

说明：
- 这类 UI 插件**不属于外部 tool 插件**（不走 `.clude/plugins/*.yaml`），主要用于代码组织与可选启用。
- `clude chat` 仍保持 `ChatHandler` 单入口；UI 仅通过参数 `--live-ui classic|enhanced` 选择渲染器。

## 业界对比

| 项目 | 插件系统 | 定义方式 | 沙箱隔离 | 安全控制 |
|:---|:---|:---|:---|:---|
| **Claude MCP** | ✅ | JSON Schema + subprocess | ✅ | ✅ 完善 |
| **Aider** | ❌ | 硬编码 | - | - |
| **Cursor** | ❌ | 内置 | - | - |
| **本项目** | ✅ | YAML/JSON | ✅ | ✅ 企业级 |

## 插件类型

### 1. Script 插件（外部脚本）

```yaml
# .clude/plugins/my_tool.yaml
name: my_tool
type: script
description: "自定义分析工具"
command: ["python", "scripts/my_tool.py"]
params:
  - name: input
    type: string
    required: true
    description: "输入数据"
  - name: verbose
    type: boolean
    default: false
timeout_s: 60
sandbox: true
```

### 2. HTTP 插件（API 调用）

```yaml
name: translate
type: http
description: "翻译 API"
url: "https://api.example.com/translate"
method: POST
headers:
  Content-Type: "application/json"
params:
  - name: text
    type: string
    required: true
  - name: target_lang
    type: string
    default: "zh"
timeout_s: 30
```

### 3. Python 插件（内嵌代码）

```yaml
name: calc
type: python
description: "简单计算器"
code: |
  result = args['a'] + args['b']
  print(f"Result: {result}")
params:
  - name: a
    type: number
    required: true
  - name: b
    type: number
    required: true
sandbox: true
```

## 安全机制

### 1. 沙箱隔离

- 工作目录限制在 workspace 内
- 移除敏感环境变量（API keys、密码等）
- 输出大小限制（防止 DoS）

### 2. 参数校验

```python
# 自动校验参数类型和必填项
for param in plugin.params:
    if param.required and param.name not in args:
        return error("Missing required parameter")
```

### 3. 企业策略集成

```python
# 结合企业策略检查插件是否被允许
decision = policy_engine.check_plugin(plugin_name)
if not decision.allowed:
    return error(decision.reason)
```

## 使用示例

### 注册插件

```python
from clude_code.plugins.registry import PluginRegistry, PluginDefinition

registry = PluginRegistry(workspace_root)

# 从文件加载
# 自动扫描 .clude/plugins/*.yaml

# 或编程方式注册
plugin = PluginDefinition(
    name="my_tool",
    type="script",
    command=["python", "my_tool.py"],
    params=[...],
)
registry.register(plugin)
```

### 执行插件

```python
result = registry.execute("my_tool", {"input": "test data"})
if result.ok:
    print(result.output)
else:
    print(f"Error: {result.error}")
```

### 工具调用格式

```json
{"tool": "plugin_execute", "args": {"name": "my_tool", "args": {"input": "test"}}}
```

## 目录结构

```
.clude/
└── plugins/
    ├── my_tool.yaml
    ├── translate.yaml
    └── calc.json
```

## 健壮性设计

- **超时保护**: 每个插件有独立的超时限制
- **进程隔离**: Script/Python 插件在子进程中执行
- **错误处理**: 命令不存在、超时、异常都有明确的错误码
- **输出截断**: 防止大输出占用过多内存

