# 开发计划清单 (Development Plan Checklist)

> **Last Updated (最后更新)**: 2026-01-18  
> **Current Milestone (当前里程碑)**: M2: Robustness (M2: 健壮性)  
> **Focus (当前重点)**: P0 基础设施加固 + P1 健壮性提升

---

## 📋 P0: 基础设施加固 (Infrastructure Hardening) - 进行中

### ✅ P0-1 Trace ID 稳定性治理 (已完成)
- [x] 引入 `uuid` 标准库
- [x] 贯穿 `AgentLoop` -> `_ev` -> `Audit` -> `UI`
- [x] 修复 `/bug` 报告归因（trace_id 贯穿与展示）

### 🔄 P0-2 控制协议结构化 (进行中)
- [ ] 定义 `{"control": "step_done"}` Schema (控制协议 Schema)
- [ ] 升级 `Execution` 解析逻辑（优先 JSON 解析，失败才回退文本匹配）
- [ ] 更新 System Prompt 约束（明确要求输出结构化控制信号）

**预期收益**: 消除模型幻觉导致的误触，提升协议鲁棒性。

### ⏳ P0-3 局部重规划 (Plan Patching) (待开始)
- [ ] 定义 `PlanPatch` 数据结构（增量变更描述）
- [ ] 实现 `Planner.patch_plan()`（仅生成增量步骤）
- [ ] 优化重规划 Prompt（强调保留已完成步骤）

**预期收益**: 降低 Token 成本，避免上下文丢失。

---

## 📋 P1: 健壮性提升 (Robustness Enhancement) - 待开始

### P1-1 异常处理规范化
- [ ] 全局扫描 `except: pass` 实例
- [ ] 替换为 `file_only_logger.warning(..., exc_info=True)`
- [ ] 添加异常分类（可恢复/不可恢复）

**预期收益**: 提升问题可观测性，避免静默失败。

### P1-2 Tool Registry 去重
- [ ] 审计所有 Tool 定义（确认 ToolSpec 为唯一真实源）
- [ ] 移除冗余定义（如 `tool_dispatch.py` 外的重复 Schema）
- [ ] 建立 Tool 版本兼容性检查

**预期收益**: 降低维护成本，避免契约不一致。

---

## 📋 P2: 体验与生态 (UX & Ecosystem) - 部分进行中

### 🔄 P2-1 RAG 深度调优 (进行中)
- [x] Tree-sitter Chunking（基于语法树分块）
- [x] Metadata Fusion（元数据融合：symbol/node_type/scope）
- [x] 基础 Rerank（基于 Metadata 加权打分）
- [ ] Hybrid Search（正式将 `rg` 结果作为 Rerank 信号）
- [ ] 并发索引优化（线程池控制）

**预期收益**: 提升代码检索精度，降低误召回。

### ⏳ P2-2 Git 工作流集成 (待开始)
- [ ] 实现 `git status` / `git diff` 工具
- [ ] 实现 Auto Commit（基于变更自动生成 Conventional Commits）
- [ ] 实现 PR Review 辅助（生成变更摘要）

**预期收益**: 对齐 Claude Code 的 Git 一等公民体验。

---

## 📋 对标 Claude Code 差距 (Claude Code Gap Analysis)

### ⚠️ 待补齐能力

| 能力项 | 当前状态 | 优先级 | 计划 |
| :--- | :--- | :--- | :--- |
| **Repo Context (200k)** | ⚠️ Gap（差距） | P1 | 需引入 Memory/Summarizer（记忆/摘要器） |
| **Git Integration** | ❌ Missing（缺失） | P2 | 见 P2-2 |
| **Usage Attribution** | ⚠️ Partial（部分完成） | P1 | 已有 Session 统计，缺详细归因（按文件/工具/步骤） |

---

## 📋 文档与生态 (Documentation & Community) - 已完成

### ✅ 文档体系完善
- [x] 故障排除 FAQ (`docs/18-troubleshooting-faq.md`)
- [x] 贡献指南 (`docs/19-contribution-guide.md`)
- [x] 文档审计报告 (`docs/DOCUMENTATION_AUDIT_REPORT.md`)
- [x] 双语注释强制化（全 docs 通过校验）

---

## 🎯 下一步行动建议 (Next Steps)

### 本周重点 (This Week)
1. **完成 P0-2**: 控制协议结构化（预计 2-3 天）
2. **启动 P0-3**: Plan Patching 数据结构设计（预计 1 天）

### 本月目标 (This Month)
1. **完成 P0 全部任务**: 基础设施加固闭环
2. **启动 P1-1**: 异常处理规范化（扫描 + 修复）

### 下季度目标 (Next Quarter)
1. **完成 P2-1**: RAG 深度调优（Hybrid Search + 并发优化）
2. **启动 P2-2**: Git 工作流集成（MVP）

---

## 📊 进度追踪 (Progress Tracking)

| 里程碑 | 完成度 | 预计完成时间 |
| :--- | :--- | :--- |
| **M2: Robustness** | 🔄 33% (1/3 P0 任务完成) | Q1 2026 |
| **M3: Intelligence** | 🔄 60% (RAG Chunking 完成，Rerank 调优中) | Q2 2026 |
| **M4: Product（产品化）** | ⏳ 0% | Q3 2026 |

---

## 🔗 相关文档 (See Also)

- **工程路线图 (Roadmap)**: [`docs/16-development-plan.md`](../docs/16-development-plan.md)
- **决策链路审计 (Audit)**: [`docs/17-agent-decision-audit.md`](../docs/17-agent-decision-audit.md)
- **文档审计报告 (Doc Audit)**: [`docs/DOCUMENTATION_AUDIT_REPORT.md`](../docs/DOCUMENTATION_AUDIT_REPORT.md)

