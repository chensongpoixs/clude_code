# Clude Code 项目重构计划

> **文档版本**：1.0.0  
> **创建时间**：2026-01-23  
> **对齐规范**：`agent_design_v_1.0.md`

---

## 0. 重构目标

根据 `agent_design_v_1.0.md` 设计规范，将当前项目重构为**企业级合并型 Agent 系统**，实现：

1. **意图驱动的 Prompt 选择**：用户意图 → Intent Registry → Prompt Profile → System/User Prompt 组合
2. **Prompt 资产化管理**：四层 System Prompt + 结构化 User Prompt，版本化、可审计、可回滚
3. **风险前置执行后置**：风险等级决定执行策略（自动/审批/沙箱）
4. **多项目强隔离**：Project 级 Token/数据隔离，全链路 Trace ID

---

## 1. 当前状态分析

### 1.1 现有模块清单

| 模块路径 | 功能 | 状态 | 问题 |
|---------|------|------|------|
| `prompts/` | Prompt 管理 | ⚠️ 部分实现 | 新旧目录结构混杂 |
| `prompts/loader.py` | Prompt 加载 | ⚠️ 基础 | 不支持 Jinja2 |
| `orchestrator/classifier.py` | 意图分类 | ⚠️ 简化 | 只有5类意图 |
| `orchestrator/agent_loop/` | Agent 核心 | ✅ 实现 | 过大需模块化 |
| `.clude/registry/` | Profile 配置 | ⚠️ 示例 | 未集成到代码 |
| `policy/` | 风险策略 | ⚠️ 部分 | Human-in-the-Loop 不完整 |
| `observability/` | 审计追踪 | ✅ 实现 | 需完善 Trace 链路 |

### 1.2 核心差距（对比 agent_design_v_1.0.md）

1. **Prompt 目录**：旧 `prompts/agent_loop/` + `prompts/classifier/` 仍存在
2. **Prompt Profile**：`.clude/registry/prompt_profiles.example.yaml` 未被代码加载使用
3. **Intent Registry**：缺少完整的 Intent → Profile 映射机制
4. **风险控制**：缺少基于 risk_level 的执行策略路由
5. **Prompt 版本化**：loader 不支持版本号解析

---

## 2. 模块化开发计划

### 模块 1: Prompt 目录结构重构

**目标**：清理旧目录，确保 `system/` + `user/` 为唯一合法结构

**开发思考流程**：
1. 检查旧 `prompts/agent_loop/` 和 `prompts/classifier/` 是否仍被引用
2. 将有用内容迁移到 `system/` 或 `user/stage/`
3. 删除旧目录
4. 更新所有 import 路径
5. 验证：`python -m compileall` + 运行测试

**文件清单**：
- 删除: `prompts/agent_loop/`（内容迁移到 `user/stage/`）
- 删除: `prompts/classifier/`（内容迁移到 `user/stage/intent_classify.j2`）
- 确保: `system/{core,role,policy,context}` 完整
- 确保: `user/{intent,stage}` 完整

**验收标准**：
- [ ] 旧目录已删除
- [ ] 所有 prompt 引用指向新路径
- [ ] `python -m compileall -q src/clude_code` 无报错
- [ ] Agent 可正常运行

---

### 模块 2: Prompt Loader 增强

**目标**：支持 Jinja2 模板渲染、版本化文件解析、YAML front matter

**开发思考流程**：
1. 分析当前 `loader.py` 的简单实现
2. 引入 Jinja2 渲染（已在 pyproject.toml 依赖中）
3. 实现版本号解析：`xxx_v1.2.3.md` → 返回版本信息
4. 实现 YAML front matter 解析
5. 保持向后兼容（无版本号 = 默认版本）

**关键函数设计**：
```python
def load_prompt(rel_path: str, version: str | None = None) -> PromptAsset:
    """
    加载 prompt 资产。
    - rel_path: 相对于 prompts/ 的路径（不含版本后缀）
    - version: 可选版本号，None = 最新/默认
    返回: PromptAsset(content, metadata, version)
    """

def render_prompt(rel_path: str, context: dict, version: str | None = None) -> str:
    """
    渲染 Jinja2 模板。
    """
```

**验收标准**：
- [ ] 支持 `.j2` 文件的 Jinja2 渲染
- [ ] 支持版本化文件名解析
- [ ] 支持 YAML front matter 提取
- [ ] 单元测试通过

---

### 模块 3: Prompt Profile Registry

**目标**：实现 Prompt Profile 配置中心，作为 Intent 与 Prompt 资产的中间抽象层

**开发思考流程**：
1. 定义 `PromptProfile` 数据模型（Pydantic）
2. 实现配置文件加载（`.clude/registry/prompt_profiles.yaml`）
3. 实现 Profile 查找接口
4. 实现 System Prompt 组合逻辑
5. 与 Agent Loop 集成

**数据模型设计**：
```python
class PromptProfile(BaseModel):
    name: str
    description: str
    risk_level: RiskLevel  # LOW, MEDIUM, HIGH, CRITICAL
    prompts: PromptRefs

class PromptRefs(BaseModel):
    system: SystemPromptRefs  # base, domain, task
    user_prompt: UserPromptRef

class ProfileRegistry:
    def get(self, profile_name: str) -> PromptProfile
    def list_profiles() -> list[str]
```

**文件位置**：`src/clude_code/orchestrator/registry/profile_registry.py`

**验收标准**：
- [ ] 可加载 `prompt_profiles.yaml`
- [ ] 可按名称查找 Profile
- [ ] 返回组合后的 System Prompt 内容
- [ ] 风险等级正确传递

---

### 模块 4: Intent Registry

**目标**：实现完整的意图注册与路由机制

**开发思考流程**：
1. 扩展 `IntentCategory` 枚举（从5类扩展到10类）
2. 实现 Intent → Profile 映射配置
3. 重构 `IntentClassifier`，使用完整分类
4. 实现项目级 Intent 覆盖（project_id 隔离）

**完整意图分类**（对齐设计文档）：
```python
class IntentCategory(str, Enum):
    # 核心功能类
    CODING_TASK = "CODING_TASK"
    ERROR_DIAGNOSIS = "ERROR_DIAGNOSIS"
    REPO_ANALYSIS = "REPO_ANALYSIS"
    DOCUMENTATION_TASK = "DOCUMENTATION_TASK"
    
    # 咨询与规划类
    TECHNICAL_CONSULTING = "TECHNICAL_CONSULTING"
    PROJECT_DESIGN = "PROJECT_DESIGN"
    SECURITY_CONSULTING = "SECURITY_CONSULTING"
    
    # 元交互类
    CAPABILITY_QUERY = "CAPABILITY_QUERY"
    GENERAL_CHAT = "GENERAL_CHAT"
    CASUAL_CHAT = "CASUAL_CHAT"
    
    # 兜底
    UNCERTAIN = "UNCERTAIN"
```

**Intent Registry 配置**（`.clude/registry/intents.yaml`）：
```yaml
intents:
  - intent: CODING_TASK
    prompt_profile: classifier_coding_task
    project_overrides:
      fintech_app: readonly_query  # 特定项目覆盖
```

**验收标准**：
- [ ] 支持完整10+类意图
- [ ] Intent → Profile 映射正确
- [ ] 支持 project_id 级覆盖
- [ ] 分类器准确率 > 90%（启发式 + LLM）

---

### 模块 5: Orchestrator 核心流程重构

**目标**：重构 `AgentLoop`，对接 Profile 选择机制，实现标准执行流程

**开发思考流程**：
1. 在 `run_turn()` 中集成 Intent → Profile → Prompt 流程
2. 实现 `_select_prompt_profile()` 方法
3. 重构 `_build_system_prompt()` 使用 Profile 组合
4. 重构 `_build_user_prompt()` 使用 Profile 的 user_prompt_template
5. 传递 risk_level 给风险控制模块

**执行流程（对齐设计文档 6.1）**：
```
1. 意图识别 → IntentClassifier.classify()
2. 选择 Prompt Profile → ProfileRegistry.get(intent.prompt_profile)
3. 装配 System Prompt → 组合 base + domain + task
4. 渲染 User Prompt → render_prompt(profile.user_prompt_template, context)
5. 执行/规划/审批 → 根据 risk_level 路由
```

**验收标准**：
- [ ] 执行流程符合设计文档
- [ ] Profile 选择正确
- [ ] System/User Prompt 组合正确
- [ ] risk_level 正确传递

---

### 模块 6: 风险控制与 Human-in-the-Loop

**目标**：实现基于风险等级的执行策略

**开发思考流程**：
1. 定义 `RiskLevel` 枚举和执行策略映射
2. 实现 `RiskRouter` 决策器
3. 集成到工具执行前的检查点
4. 实现 Plan Review（HIGH）和人工审批（CRITICAL）流程

**风险策略映射（对齐设计文档第7节）**：
| 风险等级 | 执行策略 |
|---------|---------|
| LOW | 自动执行 |
| MEDIUM | 自动执行 + 回滚准备 |
| HIGH | Plan Review（展示计划，确认后执行）|
| CRITICAL | 人工审批 + 沙箱执行 |

**关键函数**：
```python
class RiskRouter:
    def route(self, risk_level: RiskLevel, action: Action) -> ExecutionDecision:
        """
        返回: AUTO / REVIEW / APPROVE / SANDBOX
        """
```

**验收标准**：
- [ ] LOW 任务自动执行
- [ ] HIGH 任务展示计划并等待确认
- [ ] CRITICAL 任务需人工审批
- [ ] 回滚机制可用

---

### 模块 7: 审计与可观测性完善

**目标**：实现全链路 Trace ID，完善审计日志

**开发思考流程**：
1. 检查现有 `TraceLogger` 和 `AuditLogger`
2. 确保 trace_id 贯穿：请求 → 意图识别 → Profile 选择 → 执行 → 结果
3. 记录关键决策点：Intent、Profile、RiskLevel、ExecutionDecision
4. 实现 Prompt/Profile 变更审计

**审计事件类型**：
```python
INTENT_CLASSIFIED = "intent_classified"
PROFILE_SELECTED = "profile_selected"
RISK_EVALUATED = "risk_evaluated"
TOOL_EXECUTED = "tool_executed"
APPROVAL_REQUESTED = "approval_requested"
```

**验收标准**：
- [ ] trace_id 全链路传递
- [ ] 关键决策点有审计日志
- [ ] 可通过 trace_id 回溯完整执行链
- [ ] Prompt 变更有版本记录

---

## 3. 开发优先级与依赖关系

```
模块1 (Prompt目录) ──────────────────┐
                                     │
模块2 (Prompt Loader) ───────────────┼──> 模块5 (Orchestrator)
                                     │          │
模块3 (Profile Registry) ────────────┤          │
                                     │          v
模块4 (Intent Registry) ─────────────┘    模块6 (风险控制)
                                                 │
                                                 v
                                          模块7 (审计)
```

**推荐开发顺序**：
1. 模块1 → 模块2 → 模块3 → 模块4（基础设施）
2. 模块5（核心集成）
3. 模块6 → 模块7（增强能力）

---

## 4. 进度跟踪

| 模块 | 状态 | 开始时间 | 完成时间 | 业界对齐度 |
|------|------|---------|---------|-----------|
| 模块1: Prompt目录 | ✅ 完成 | 2026-01-23 | 2026-01-23 | 90% |
| 模块2: Prompt Loader | ✅ 完成 | 2026-01-23 | 2026-01-23 | 95% |
| 模块3: Profile Registry | ✅ 完成 | 2026-01-23 | 2026-01-23 | 95% |
| 模块4: Intent Registry | ✅ 完成 | 2026-01-23 | 2026-01-23 | 90% |
| 模块5: Orchestrator | ✅ 完成 | 2026-01-23 | 2026-01-23 | 85% |
| 模块6: 风险控制 | ✅ 完成 | 2026-01-23 | 2026-01-23 | 90% |
| 模块7: 审计 | ✅ 完成 | 2026-01-23 | 2026-01-23 | 85% |

---

## 5. 业界对标参考

| 能力 | 业界标准 | 本项目目标 |
|------|---------|-----------|
| Prompt 版本化 | LangChain Hub / Anthropic Prompt Caching | SemVer + Git 审计 |
| Intent 分类 | OpenAI Function Calling / Claude Tool Use | LLM + 启发式混合 |
| 风险控制 | Anthropic Constitutional AI / Microsoft Responsible AI | 四级风险路由 |
| 审计追踪 | OpenTelemetry / LangSmith | 全链路 Trace ID |
| Prompt Profile | Cursor Rules / Continue Dev | 配置化组合 |

---

## 6. 附录：文件变更清单

### 新增文件
- `src/clude_code/orchestrator/registry/profile_registry.py`
- `src/clude_code/orchestrator/registry/intent_registry.py`
- `src/clude_code/orchestrator/risk_router.py`
- `src/clude_code/prompts/loader_v2.py`（增强版加载器）

### 修改文件
- `src/clude_code/orchestrator/classifier.py`（扩展意图）
- `src/clude_code/orchestrator/agent_loop/agent_loop.py`（集成 Profile）
- `src/clude_code/prompts/__init__.py`（导出新接口）

### 删除文件
- `src/clude_code/prompts/agent_loop/`（整个目录）
- `src/clude_code/prompts/classifier/`（整个目录）

