# Intent Registry 意图注册表

> 文档版本: 1.0  
> 创建日期: 2026-01-22

## 概述

Intent Registry 是 Clude Code 的意图配置系统，允许通过 YAML 文件定义项目级意图配置，用于：
- **精确控制 Agent 行为**：按意图限制可用工具
- **风险分级管理**：不同意图可设置不同风险等级
- **Prompt 版本化**：按 stage 绑定三层 Prompt（base/domain/task）并支持 SemVer 与运营切换（`prompt_versions.json`）
- **热加载更新**：修改配置后无需重启

---

## 配置文件位置

```
{workspace_root}/.clude/registry/intents.yaml
```

---

## 配置 Schema

### 完整示例

```yaml
version: "1.0"
default_risk_level: MEDIUM
default_mode: unified

prompts:
  planning:
    base: { ref: "base/planning.j2", version: "1.0.0" }
    domain: { ref: "domains/planning_coding.j2", version: "1.0.0" }
    task: { ref: "tasks/planning_default.j2" } # version 省略 -> prompt_versions.json current
  execute_step:
    base: { ref: "base/security.md", version: "1.0.0" }
    domain: { ref: "domains/agent_loop.md", version: "1.0.0" }
    task: { ref: "tasks/execute_step.j2", version: "1.0.0" }

intents:
  - name: code_review
    description: "代码审查任务"
    keywords:
      - "review"
      - "审查"
      - "code review"
    mode: unified
    risk_level: LOW
    # 意图级覆盖（可选）：只覆盖需要差异化的 stage
    # prompts:
    #   planning:
    #     task: { ref: "tasks/planning_code_review.j2", version: "1.0.0" }
    tools:
      - read_file
      - grep
      - list_dir
    priority: 10
    enabled: true
```

### 字段说明

| 字段 | 类型 | 必填 | 默认值 | 说明 |
| :--- | :--- | :---: | :--- | :--- |
| `version` | string | 否 | "1.0" | 配置版本号 |
| `default_risk_level` | enum | 否 | MEDIUM | 默认风险等级 |
| `default_mode` | string | 否 | unified | 默认执行模式 |
| `intents` | list | 是 | [] | 意图列表 |

### IntentSpec 字段

| 字段 | 类型 | 必填 | 默认值 | 说明 |
| :--- | :--- | :---: | :--- | :--- |
| `name` | string | **是** | - | 意图唯一标识 |
| `keywords` | list[str] | 否 | [] | 触发关键词 |
| `mode` | string | 否 | unified | unified / split |
| `risk_level` | enum | 否 | MEDIUM | LOW/MEDIUM/HIGH/CRITICAL |
| `prompts` | object | 否 | null | 按阶段(stage)的三层 Prompt 选择（intent 级覆盖） |
### Prompt 版本切换（可运营）

在 `.clude/registry/intents.yaml` 里只需要指定 **ref**（文件路径）；是否固定某版本由你选择：

- **固定版本**：写死 `version: "1.0.0"`（强绑定）
- **运营切换**：`version` 为空，让 PromptManager 读取：
  - `.clude/registry/prompt_versions.json.prompts[ref].current`
  - 并支持 `previous` 回滚指针

#### CLI 运维命令（推荐）

项目提供 `clude prompts` 子命令来安全修改 `prompt_versions.json`（避免手工改 JSON 出错）：

```bash
# 查看全部版本指针
clude prompts show

# 查看某个 ref
clude prompts show tasks/planning_default.j2

# 固定（pin）某个 ref 的 current 版本（自动记录 previous）
clude prompts pin tasks/planning_default.j2 1.0.0

# 回滚：current <-> previous
clude prompts rollback tasks/planning_default.j2

# 清空：移除该 ref 的版本指针
clude prompts unpin tasks/planning_default.j2

# 校验：检查 ref/版本文件/front matter 合规（推荐上线前跑一次）
clude prompts validate
```

| `tools` | list[str] | 否 | [] | 允许的工具（空=不限） |
| `description` | string | 否 | null | 意图描述 |
| `enabled` | bool | 否 | true | 是否启用 |
| `priority` | int | 否 | 0 | 优先级（越大越优先） |

### 风险等级

| 等级 | 说明 | 默认行为 |
| :--- | :--- | :--- |
| `LOW` | 只读操作 | 自动执行 |
| `MEDIUM` | 可逆写操作 | 需要确认 |
| `HIGH` | 不可逆操作 | 需要显式确认 |
| `CRITICAL` | 高危操作 | 需要审批（未来） |

---

## 使用方式

### CLI

```bash
# 默认使用 project_id="default"
clude chat

# 指定项目 ID（使用该项目的意图配置）
clude chat --project-id=myproject
```

### Python API

```python
from clude_code.orchestrator.registry import IntentRegistry, IntentRouter

# 加载注册表
registry = IntentRegistry("/path/to/workspace")

# 获取配置
config = registry.get_config()
print(f"已加载 {len(config.intents)} 个意图")

# 创建路由器
router = IntentRouter(registry)

# 路由用户输入
match = router.route("帮我审查这段代码")
print(f"意图: {match.name}, 风险: {match.risk_level}, 工具: {match.tools}")
```

---

## 路由优先级

1. **精确关键词匹配**：用户输入包含完整关键词
2. **模糊关键词匹配**：部分关键词匹配（置信度 ≥ 30%）
3. **LLM 意图分类**：回退到 IntentClassifier（可选）
4. **默认配置**：无匹配时使用

---

## 热加载

Intent Registry 支持 mtime 热加载：
- 检测到 `intents.yaml` 文件变更后自动重载
- 无需重启 Agent 或 CLI

---

## 示例配置

完整示例请参考：
- `.clude/registry/intents.example.yaml`

---

## 与现有系统集成

Intent Registry 与以下系统协同工作：

| 系统 | 集成点 | 说明 |
| :--- | :--- | :--- |
| **ProjectPaths** | 路径计算 | 配置文件路径 |
| **IntentClassifier** | 回退分类 | Registry 无匹配时使用 |
| **ToolRegistry** | 工具限制 | 按意图限制可用工具 |
| **RiskAssessor** | 风险评估 | 使用意图风险等级 |

---

## 后续规划

- [ ] **P2**: 多意图命中冲突消解（conflict resolver）
- [ ] **P2**: Prompt 灰度发布（AB/权重切换）
- [ ] **P2**: 冲突消解（多意图命中时）
- [ ] **P2**: 项目级工具限制

