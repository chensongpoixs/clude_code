# 17 | Agent 决策链路深度审计报告 (Decision Audit Report)

> **Audit Target (审计对象)**: `AgentLoop` Decision Chain (决策链路)  
> **Status (状态)**: Completed (已完成)  
> **Verdict (结论)**: Critical Infrastructure Upgrades Required (关键基础设施需升级，P0)

---

## 1. 审计综述 (Executive Summary)

本报告对 Clude Code 的核心决策链路（意图识别 → 规划 → 执行 → 反馈）进行了代码级审计。

**结论**: 当前架构已具备闭环能力，但在**可追溯性 (Traceability)** 和 **协议稳定性 (Protocol Stability)** 方面存在结构性短板。这导致在复杂长程任务中容易出现“状态丢失”或“死循环”。

> **Status Update (状态更新)**: `P0-1 Trace ID` 已按本报告建议落地（`hash()` ➜ `uuid4().hex`），文档与实现现已对齐。

### 核心发现 (Top Findings)

1.  🚨 **Trace ID 不稳定 (P0)**: 依赖 Hash Seed，导致日志跨进程无法关联，可观测性失效。
2.  🚨 **控制协议脆弱 (P0)**: 依赖字符串匹配 (`STEP_DONE`)，易受模型幻觉干扰。
3.  ⚠️ **重规划成本高 (P1)**: 全量重写 Plan 导致 Token 浪费和上下文遗忘。

---

## 2. 深度评分与对比 (Deep Dive & Scoring)

我们采用 1-5 分制对关键模块进行量化评估（1=不可用, 5=工业级）。

### 2.1 Trace ID 生成机制

| 维度 | 当前实现 (As-Is) | 目标方案 (To-Be) | 评分变化 |
| :--- | :--- | :--- | :--- |
| **Method (方法)** | `hash((session_id, text))` | `uuid4().hex` | `1/5` ➔ `5/5` |
| **Stability (稳定性)** | ❌ 跨进程变异 | ✅ 全局唯一持久 | 🔺 Critical (关键) |
| **Impact (影响)** | 日志无法归因，Bug 难复现 | 全链路可追踪 | - |

**Recommendation**: 立即替换为 `uuid4`，并贯穿 `_ev` 事件流。

### 2.2 步骤控制协议 (Control Protocol)

| 维度 | 当前实现 (As-Is) | 目标方案 (To-Be) | 评分变化 |
| :--- | :--- | :--- | :--- |
| **Method (方法)** | String Match (字符串匹配, `"STEP_DONE"`) | JSON Envelope (JSON 信封, `{"control": "step_done"}` / `{"control":"replan"}`) | `2/5` ➔ `4.5/5` |
| **Robustness (鲁棒性)** | ❌ 易误触 (Hallucination/幻觉) | ✅ 结构化无歧义 | 🔺 High (高) |

**Recommendation**: 定义严格的 Control Schema，优先尝试 JSON 解析。

### 2.3 重规划策略 (Replanning)

| 维度 | 当前实现 (As-Is) | 目标方案 (To-Be) | 评分变化 |
| :--- | :--- | :--- | :--- |
| **Method (方法)** | Full Rewrite (全量重写) | Plan Patching (计划补丁) | `2/5` ➔ `4.5/5` |
| **Cost (成本)** | 💸 High Token Cost (高 Token 成本) | 💰 Low (Delta only / 仅增量) | 🔺 High (高) |
| **Context (上下文)** | ❌ 易丢失历史 | ✅ 保留 Done Steps (已完成步骤) | - |

**Recommendation**: 引入 `PlanPatch` 数据结构，仅生成增量变更。

---

## 3. 详细改进计划 (Implementation Plan)

### 3.1 P0: 基础设施重构

#### Task 1: Trace ID Migration（迁移 Trace ID）
```python
# Before (修改前)
trace_id = f"trace_{abs(hash((self.session_id, user_text)))}"

# After (修改后)
import uuid
trace_id = f"trace_{uuid.uuid4().hex}"
```
*   **验收标准**: 同一输入多次运行生成不同 ID；跨进程 ID 格式合法。

#### Task 2: Protocol Structuring（协议结构化）
*   **Prompt Update（提示词更新）**: 明确要求输出 `{"control": "step_done"}`。
*   **Parser Logic（解析逻辑）**:
    1.  Extract JSON candidate（提取 JSON 候选）。
    2.  Validate against `ControlSchema`（按控制协议 Schema 校验）。
    3.  Fallback to text only if validation fails（校验失败才回退到文本规则）。

### 3.2 P1: 健壮性提升

*   **复读检测**: 引入 N-gram 重复率检测，替代简单的字符计数。
*   **异常捕获**: 全局移除 `except: pass`，强制记录 Warning 日志。

---

## 4. 链路图解 (Decision Flow)

![Decision Flow](../src/assets/decision_flow.svg)
