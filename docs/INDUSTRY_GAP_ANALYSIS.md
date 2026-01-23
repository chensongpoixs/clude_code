# Clude Code 业界对标分析与下一步计划

> **文档版本**：1.0.0  
> **分析时间**：2026-01-23  
> **对标规范**：`agent_design_v_1.0.md`

---

## 1. 总体评估

### 1.1 完成度概览

| 模块 | 当前完成度 | 业界对齐度 | 主要差距 |
|------|-----------|-----------|---------|
| Prompt 目录结构 | 95% | 90% | 旧目录残留未完全清理 |
| Prompt Loader | 90% | 95% | 版本回滚 CLI 缺失 |
| Profile Registry | 85% | 90% | 配置热重载、持久化 |
| Intent Registry | 80% | 85% | LLM+关键词融合策略 |
| Orchestrator 集成 | **60%** | 70% | **Profile 动态组合未生效** |
| Risk Router | 70% | 75% | **未集成到执行流程** |
| Sandbox 执行 | **0%** | 0% | **完全未实现** |
| Approvals 审批 | **0%** | 0% | **完全未实现** |
| 审计追踪 | 75% | 80% | 事件标准化、可视化 |
| 多项目隔离 | 40% | 50% | 项目级配置覆盖 |

### 1.2 风险评估

| 风险等级 | 模块 | 影响 |
|---------|------|------|
| 🔴 高 | Orchestrator 集成 | Profile 选择后未实际使用，设计意图未落地 |
| 🔴 高 | Sandbox/Approvals | CRITICAL 风险操作无保护机制 |
| 🟡 中 | RiskRouter 集成 | 风险策略已定义但未执行 |
| 🟡 中 | Prompt 版本管理 | 无法便捷回滚问题版本 |
| 🟢 低 | RAG 优化 | 功能可用，但可进一步优化 |

---

## 2. 模块详细分析

### 2.1 模块1：Prompt 目录结构

**当前状态**：✅ 基本完成

**已实现**：
- `system/{core,role,policy,context}` 四层结构 ✅
- `user/{stage,intent}` 分层结构 ✅
- 意图模板按业务域分组（dev/analysis/design/security/meta/chat）✅

**未完善**：
- 旧目录 `prompts/agent_loop/` 和 `prompts/classifier/` 文件已删除，但 `__pycache__` 可能残留
- 部分代码可能仍引用旧路径（需全面扫描）

**业界对标**：
| 业界标准 | 本项目 | 差距 |
|---------|-------|------|
| Cursor Rules 分层 | 四层 System Prompt | ✅ 对齐 |
| Anthropic Prompt 分类 | user/intent 分组 | ✅ 对齐 |
| LangChain Hub 结构 | 目录约定 | ⚠️ 缺少 metadata.json |

**下一步**：
1. [ ] 清理所有 `__pycache__` 残留
2. [ ] 添加 `prompts/metadata.json` 描述目录结构
3. [ ] 全面扫描旧路径引用

---

### 2.2 模块2：Prompt Loader

**当前状态**：✅ 基本完成

**已实现**：
- Jinja2 模板渲染 ✅
- 版本化文件名解析（`xxx_v1.2.3.md`）✅
- YAML front matter 解析 ✅
- `PromptAsset` 数据模型 ✅
- `render_system_prompt()` 四层组合 ✅
- 优雅降级（Jinja2 不可用时使用简单替换）✅

**未完善**：
- 缺少版本回滚 CLI 命令
- 缺少版本锁定/切换机制
- 缺少 Prompt 变更审计

**业界对标**：
| 业界标准 | 本项目 | 差距 |
|---------|-------|------|
| LangChain Hub 版本化 | SemVer 文件名 | ✅ 对齐 |
| Anthropic Prompt Caching | 缓存机制 | ❌ 未实现 |
| MLOps 元数据 | YAML front matter | ✅ 对齐 |
| Git 版本审计 | 配合 Git | ⚠️ 可增强 |

**下一步**：
1. [ ] 实现 `clude prompts rollback <version>` CLI
2. [ ] 实现 `clude prompts lock <profile>` 版本锁定
3. [ ] 添加 Prompt 变更审计日志
4. [ ] 考虑 Prompt 缓存优化（减少重复读取）

---

### 2.3 模块3：Profile Registry

**当前状态**：✅ 基本完成

**已实现**：
- `PromptProfile` 数据模型 ✅
- `ProfileRegistry` 配置加载 ✅
- `get_system_prompt()` 四层组合 ✅
- `render_user_prompt()` 模板渲染 ✅
- `get_by_intent()` 意图映射 ✅
- 单例模式 `get_default_registry()` ✅

**未完善**：
- 配置热重载（修改 YAML 后需重启）
- Profile 验证（引用的 Prompt 文件是否存在）
- Profile 依赖检查

**业界对标**：
| 业界标准 | 本项目 | 差距 |
|---------|-------|------|
| Cursor Rules 配置 | YAML 配置 | ✅ 对齐 |
| LangSmith 版本控制 | 版本字段 | ✅ 对齐 |
| 热重载机制 | 无 | ❌ 需实现 |
| 配置验证 | 无 | ❌ 需实现 |

**下一步**：
1. [ ] 实现配置热重载（文件监听）
2. [ ] 添加 Profile 验证器（检查引用文件存在性）
3. [ ] 添加 Profile 依赖关系图
4. [ ] 考虑 Profile 继承/组合机制

---

### 2.4 模块4：Intent Registry

**当前状态**：⚠️ 需完善

**已实现**：
- `IntentCategory` 11类完整枚举 ✅
- `IntentRegistry` 配置加载 ✅
- 关键词匹配 `match_by_keywords()` ✅
- Intent → Profile 映射 ✅
- project_id 级覆盖支持 ✅

**未完善**：
- LLM 分类结果与关键词匹配未融合
- 分类置信度阈值配置
- 意图识别准确率监控

**业界对标**：
| 业界标准 | 本项目 | 差距 |
|---------|-------|------|
| OpenAI Function Calling | 11类意图 | ✅ 对齐 |
| 混合分类策略 | 仅 LLM | ❌ 需融合关键词 |
| 分类准确率监控 | 无 | ❌ 需实现 |
| A/B 测试支持 | 无 | ❌ 可选 |

**下一步**：
1. [ ] 实现 LLM + 关键词混合分类策略
2. [ ] 添加分类置信度阈值配置
3. [ ] 实现分类准确率监控与报告
4. [ ] 考虑意图识别的 Few-shot 优化

---

### 2.5 模块5：Orchestrator 核心集成 ⚠️ 关键问题

**当前状态**：🔴 需重点完善

**已实现**：
- `ProfileRegistry` 实例化 ✅
- `_select_profile()` 方法 ✅
- `_current_profile` 和 `_current_risk_level` 属性 ✅
- 意图分类后调用 `_select_profile()` ✅

**⚠️ 关键问题：Profile 选择后未实际使用**

```python
# 当前代码（agent_loop.py:218-222）
combined_system_prompt = (
    f"{SYSTEM_PROMPT}"  # ❌ 仍使用硬编码 SYSTEM_PROMPT
    f"{project_memory_text}"
    f"\n\n=== 环境信息 ===\n{env_info}\n\n=== 代码仓库符号概览 ===\n{repo_map}"
)
```

**应该改为**：
```python
# 使用 Profile 动态组合
system_prompt = self._current_profile.get_system_prompt(
    tools_section=tools_section,
    project_memory=project_memory_text,
    env_info=env_info,
) if self._current_profile else SYSTEM_PROMPT
```

**业界对标**：
| 业界标准 | 本项目 | 差距 |
|---------|-------|------|
| 动态 Prompt 组合 | 硬编码 | ❌ **核心差距** |
| Profile 驱动执行 | 设置但未用 | ❌ **核心差距** |
| 风险等级传递 | 设置但未用 | ❌ 需完善 |

**下一步（优先级：高）**：
1. [ ] **重构 `__init__` 和 `run_turn`，使用 Profile 动态组合 System Prompt**
2. [ ] **使用 Profile 的 `render_user_prompt()` 渲染 User Prompt**
3. [ ] **传递 `_current_risk_level` 给 RiskRouter**
4. [ ] 添加 Profile 切换日志

---

### 2.6 模块6：风险控制与 Human-in-the-Loop ⚠️ 关键问题

**当前状态**：🟡 部分实现

**已实现**：
- `RiskRouter` 风险路由器 ✅
- 四级风险策略映射 ✅
- `ExecutionDecision` 决策模型 ✅
- `format_plan_review_prompt()` ✅
- `format_approval_request()` ✅

**⚠️ 关键问题：RiskRouter 未集成到执行流程**

当前代码中 `RiskRouter` 已创建但未在工具执行前调用：

```python
# 应该在工具执行前添加
risk_decision = risk_router.route(
    risk_level=self._current_risk_level,
    tool_name=tool_name,
)
if risk_decision.requires_confirmation:
    # 触发确认流程
```

**业界对标**：
| 业界标准 | 本项目 | 差距 |
|---------|-------|------|
| Constitutional AI | 四级策略 | ✅ 设计对齐 |
| 策略执行 | 未集成 | ❌ **核心差距** |
| Plan Review | 格式化函数 | ⚠️ 未集成到流程 |
| 人工审批 | 格式化函数 | ⚠️ 未集成到流程 |

**下一步（优先级：高）**：
1. [ ] **在 `_run_tool_lifecycle` 中集成 RiskRouter**
2. [ ] **实现 HIGH 风险的 Plan Review 流程**
3. [ ] 实现 CRITICAL 风险的审批流程
4. [ ] 添加风险评估日志

---

### 2.7 模块7：Sandbox 执行 🔴 完全未实现

**当前状态**：❌ 未实现

`src/clude_code/orchestrator/sandbox/` 目录存在但为空。

**业界需求**：
- CRITICAL 风险操作应在隔离环境执行
- 支持操作预览（Dry-run）
- 支持影响范围预估

**业界对标**：
| 业界标准 | 本项目 | 差距 |
|---------|-------|------|
| Docker 沙箱 | 无 | ❌ 未实现 |
| Dry-run 模式 | 无 | ❌ 未实现 |
| 影响预估 | 无 | ❌ 未实现 |

**下一步（优先级：中）**：
1. [ ] 设计沙箱执行架构
2. [ ] 实现 Dry-run 模式（命令预览）
3. [ ] 实现文件操作影响预估
4. [ ] 考虑 Docker/容器化方案

---

### 2.8 模块8：Approvals 审批 🔴 完全未实现

**当前状态**：❌ 未实现

`src/clude_code/orchestrator/approvals/` 目录存在但为空。

**业界需求**：
- CRITICAL 操作需人工审批
- 审批记录持久化
- 审批超时处理

**业界对标**：
| 业界标准 | 本项目 | 差距 |
|---------|-------|------|
| 审批工作流 | 无 | ❌ 未实现 |
| 审批记录 | 无 | ❌ 未实现 |
| 多级审批 | 无 | ❌ 未实现 |

**下一步（优先级：中）**：
1. [ ] 设计审批流程模型
2. [ ] 实现审批请求/响应机制
3. [ ] 实现审批记录持久化
4. [ ] 添加审批超时处理

---

### 2.9 模块9：审计与可观测性

**当前状态**：⚠️ 需完善

**已实现**：
- `AuditLogger` JSONL 审计日志 ✅
- `TraceLogger` 追踪日志 ✅
- `AuditEventType` 事件常量 ✅
- trace_id 全链路传递 ✅

**未完善**：
- 关键事件未全部记录
- 缺少审计日志可视化
- 缺少告警机制

**业界对标**：
| 业界标准 | 本项目 | 差距 |
|---------|-------|------|
| OpenTelemetry | JSONL 日志 | ⚠️ 格式差异 |
| LangSmith 可视化 | 无 | ❌ 需实现 |
| 告警机制 | 无 | ❌ 需实现 |

**下一步**：
1. [ ] 确保所有关键事件都有审计记录
2. [ ] 实现审计日志查询 CLI
3. [ ] 考虑 OpenTelemetry 兼容格式
4. [ ] 添加异常告警机制

---

### 2.10 模块10：多项目隔离

**当前状态**：⚠️ 部分实现

**已实现**：
- project_id 概念存在
- Intent Registry 支持 project_overrides

**未完善**：
- 项目级配置目录结构未定义
- 项目切换机制不完整
- Token 隔离未实现

**业界对标**：
| 业界标准 | 本项目 | 差距 |
|---------|-------|------|
| 项目隔离 | 概念存在 | ⚠️ 未落地 |
| 配置覆盖 | intent 支持 | ⚠️ profile 未支持 |
| Token 隔离 | 无 | ❌ 未实现 |

**下一步**：
1. [ ] 定义 `.clude/projects/<project_id>/` 结构
2. [ ] 实现项目级 Profile 覆盖
3. [ ] 实现项目切换命令
4. [ ] 考虑 Token 隔离方案

---

## 3. 下一步计划（优先级排序）

### P0 - 必须立即修复（阻塞核心功能）

| 序号 | 任务 | 模块 | 工作量 |
|------|------|------|--------|
| P0-1 | **Profile 动态组合 System Prompt** | Orchestrator | 2h |
| P0-2 | **Profile 渲染 User Prompt** | Orchestrator | 1h |
| P0-3 | **RiskRouter 集成到工具执行** | Risk Control | 2h |
| P0-4 | **risk_level 传递并生效** | Orchestrator | 1h |

### P1 - 高优先级（影响功能完整性）

| 序号 | 任务 | 模块 | 工作量 |
|------|------|------|--------|
| P1-1 | 实现 Plan Review 确认流程 | Risk Control | 3h |
| P1-2 | 实现 Prompt 版本回滚 CLI | Prompt Loader | 2h |
| P1-3 | 配置热重载机制 | Profile Registry | 3h |
| P1-4 | LLM + 关键词混合分类 | Intent Registry | 2h |

### P2 - 中优先级（增强能力）

| 序号 | 任务 | 模块 | 工作量 |
|------|------|------|--------|
| P2-1 | 设计并实现 Sandbox 模块 | Sandbox | 8h |
| P2-2 | 设计并实现 Approvals 模块 | Approvals | 6h |
| P2-3 | 审计日志查询 CLI | Observability | 2h |
| P2-4 | 多项目配置覆盖 | Multi-Project | 4h |

### P3 - 低优先级（优化项）

| 序号 | 任务 | 模块 | 工作量 |
|------|------|------|--------|
| P3-1 | Prompt 缓存优化 | Prompt Loader | 2h |
| P3-2 | 分类准确率监控 | Intent Registry | 3h |
| P3-3 | OpenTelemetry 兼容 | Observability | 4h |
| P3-4 | 清理旧代码残留 | All | 1h |

---

## 4. 业界最佳实践参考

### 4.1 Prompt 工程

| 实践 | 参考项目 | 本项目状态 |
|------|---------|-----------|
| Prompt 版本化 | LangChain Hub | ✅ 已实现 |
| Prompt 测试 | Promptfoo | ❌ 未实现 |
| Prompt 缓存 | Anthropic | ❌ 未实现 |
| Prompt A/B 测试 | LangSmith | ❌ 未实现 |

### 4.2 Agent 编排

| 实践 | 参考项目 | 本项目状态 |
|------|---------|-----------|
| 意图识别 | OpenAI Function Calling | ✅ 已实现 |
| 多 Agent 协作 | AutoGen | ❌ 未实现 |
| 状态机 | LangGraph | ⚠️ 基础实现 |
| 工具编排 | Tool Use | ✅ 已实现 |

### 4.3 安全与合规

| 实践 | 参考项目 | 本项目状态 |
|------|---------|-----------|
| 风险分级 | Constitutional AI | ✅ 已设计 |
| 沙箱执行 | Docker | ❌ 未实现 |
| 审批流程 | Enterprise AI | ❌ 未实现 |
| 审计日志 | OpenTelemetry | ⚠️ 基础实现 |

---

## 5. 里程碑规划

### Milestone 1：核心集成完善（1周）
- [ ] P0-1 ~ P0-4：Profile 和 RiskRouter 完全集成
- [ ] P1-1：Plan Review 确认流程
- 目标：设计意图完全落地

### Milestone 2：功能增强（2周）
- [ ] P1-2 ~ P1-4：版本管理、热重载、混合分类
- [ ] P2-1 ~ P2-2：Sandbox 和 Approvals 基础实现
- 目标：企业级功能完整

### Milestone 3：可观测性与优化（1周）
- [ ] P2-3 ~ P2-4：审计查询、多项目支持
- [ ] P3-1 ~ P3-4：性能优化、代码清理
- 目标：生产就绪

---

## 6. 附录：文件检查清单

### 需要修改的文件
- [ ] `src/clude_code/orchestrator/agent_loop/agent_loop.py` - Profile 集成
- [ ] `src/clude_code/orchestrator/agent_loop/tool_lifecycle.py` - RiskRouter 集成
- [ ] `src/clude_code/orchestrator/classifier.py` - 混合分类
- [ ] `src/clude_code/prompts/loader.py` - 版本回滚

### 需要新建的文件
- [ ] `src/clude_code/orchestrator/sandbox/runner.py` - 沙箱执行器
- [ ] `src/clude_code/orchestrator/approvals/store.py` - 审批存储
- [ ] `src/clude_code/cli/prompts_cmd.py` - Prompt CLI（如不存在）

### 需要清理的文件
- [ ] `src/clude_code/prompts/agent_loop/__pycache__/` - 旧缓存
- [ ] `src/clude_code/prompts/classifier/__pycache__/` - 旧缓存

