## prompts 目录说明

> 目的：将工程里"发给大模型的提示词（prompt）"集中管理，避免散落在逻辑代码中导致难维护、难审计、难复用。

### 目录结构（对齐 agent_design_v_1.0.md）

```text
prompts/
├── system/                          # System Prompt 资产
│   ├── core/
│   │   └── global.md                # 全局规范/安全边界（必选）
│   ├── role/
│   │   ├── developer.md             # 角色：开发
│   │   ├── analyst.md               # 角色：分析
│   │   ├── architect.md             # 角色：架构
│   │   ├── operator.md              # 角色：运维
│   │   ├── security.md              # 角色：安全
│   │   ├── developer_readonly.md    # 组合角色（开发+只读策略）
│   │   ├── operator_high_risk.md    # 组合角色（运维+高风险策略）
│   │   └── security_high_risk.md    # 组合角色（安全+高风险策略）
│   ├── policy/
│   │   ├── readonly.md              # 只读策略
│   │   └── high_risk.md             # 高风险策略
│   └── context/
│       └── runtime.j2               # 运行期上下文（工具清单/项目记忆/环境信息）
└── user/                            # User Prompt 资产
    ├── stage/                       # 阶段协议提示词
    │   ├── planning.j2              # 规划阶段
    │   ├── execute_step.j2          # 执行步骤
    │   ├── replan.j2                # 重规划
    │   ├── intent_classify.j2       # 意图分类
    │   ├── plan_parse_retry.md      # 规划解析重试
    │   ├── plan_patch_retry.j2      # 规划补丁重试
    │   └── invalid_step_output_retry.md  # 无效输出重试
    └── intent/                      # 意图模板提示词（按业务域分组）
        ├── dev/                     # 开发执行类
        │   ├── coding_task.j2
        │   └── error_diagnosis.j2
        ├── analysis/                # 分析解释类
        │   ├── repo_analysis.j2
        │   ├── documentation_task.j2
        │   └── technical_consulting.j2
        ├── design/                  # 架构设计类
        │   └── project_design.j2
        ├── security/                # 安全类
        │   └── security_consulting.j2
        ├── meta/                    # 元交互/兜底
        │   ├── query.j2
        │   └── capability_query.j2
        └── chat/                    # 对话类
            ├── general_chat.j2
            └── casual_chat.j2
```

### System Prompt 四层模型

| 层级 | 目录 | 职责 | 是否必选 |
|------|------|------|---------|
| Core | `system/core/` | 全局规范/价值观/安全边界 | 必选 |
| Role | `system/role/` | Agent 角色能力与约束 | 必选 |
| Policy | `system/policy/` | 风险/合规/权限策略 | 按需 |
| Context | `system/context/` | 运行期上下文注入 | 推荐 |

### 模板变量约定

**`system/context/runtime.j2`：**
- `tools_section`：可用工具清单
- `project_memory`：项目记忆（CLUDE.md/CLAUDE.md）
- `env_info`：环境信息（含 repo_map）

**`user/intent/*/*.j2`：**
- `user_text`：原始用户输入
- `planning_prompt`：规划协议提示词
- `project_id`：项目 ID
- `intent_name`：识别出的意图名称
- `risk_level`：风险等级

**`user/stage/*.j2`：**
- 各阶段特定变量（见模板内定义）

### 文件类型与版本化

- `*.md`：纯文本提示词（无变量）
- `*.j2`：Jinja2 模板提示词（有变量占位符）
- 默认版本：`xxx.md` / `xxx.j2`
- 指定版本：`xxx_v1.2.3.md` / `xxx_v1.2.3.j2`

### 遗留目录（已废弃）

旧目录 `agent_loop/` 和 `classifier/` 已迁移到新结构，保留为空目录供兼容检查。
**新代码请使用 `system/` 和 `user/` 目录。**
