# 合并型 Agent 工程设计文档 (企业落地增强版)

## 设计目标

\> \*\*适用对象\*\*：自动执行型 Agent、复杂工程任务、生产级 AI 系统&#x20;

\> \*\*设计目标\*\*：解决「自动执行不可控」「Prompt 职责混乱」「任务不可审计」等核心问题



异常管理、版本控制、审计合规和多项目隔离增强，支持跨项目、多场景的 Agent 快速平替与安全运行。

---

## 一、核心架构升级：配置驱动流 + 异常管理

```text
用户输入 (Project_ID: A)
   │
   ▼
意图识别 (限定项目范围 + 多轮上下文) ───┐
   │                                     │
   ▼                                 [Registry 映射]
意图路由 (Intent Router) <────────────────┘
 ├─ 简单任务 (Unified) ─> 加载 Base + Task Prompt ─> 执行 + 异常处理
 └─ 复杂任务 (Split)   ─> 加载 Base + Domain + Task Prompt ─> Planner ─> 审批/执行
```

**增强点**：

- 异常管理：Executor/Planner 支持自动重试、限次数回退、失败告警
- 上下文管理：支持多轮对话意图识别、模糊匹配冲突解决

---

## 二、提示词工程体系 (Prompt Engineering)

### 2.1 三层继承模型 + 版本管理

1. **Base Layer (全局层)**：AI 基础价值观、输出格式规范、通用禁令。
2. **Domain Layer (领域层)**：注入项目/行业知识库。
3. **Task Layer (任务层)**：工具调用逻辑和 SOP 步骤。

**增强点**：

- Prompt 支持 Semantic Versioning
- Prompt ID + 版本号绑定 Orchestrator
- 可回滚到前一稳定版本

### 2.2 目录结构规范

```text
prompts/
├── base/
│   └── global_core_v2.j2
├── domains/
│   ├── cloud_ops/
│   └── fintech/
└── tasks/
    ├── project_alpha/
    │   ├── query_balance_v1.2.j2
    │   └── transfer_money_v1.3.j2
    └── project_beta/
        └── restart_node_v1.0.j2
```

---

## 三、意图注册表 (Intent Registry)

使用 YAML 管理，实现“代码与逻辑分离”。

```yaml
projects:
  - project_id: "fintech_app"
    domain: "fintech"
    intents:
      - name: "transfer"
        mode: "split"
        risk_level: "CRITICAL"
        prompt_ref: "tasks/project_alpha/transfer_money_v1.3.j2"
        tools: ["bank_api", "sms_verify"]
        version: "1.3"
      - name: "get_rate"
        mode: "unified"
        risk_level: "LOW"
        prompt_ref: "tasks/project_alpha/query_balance_v1.2.j2"
        version: "1.2"
```

**增强点**：

- Prompt 版本绑定
- 支持动态热加载 Intent
- 支持上下文追踪多轮对话

---

## 四、风险控制与审批流 (Human-in-the-loop)

| 风险等级     | 处理策略         | 审计要求                       |
| -------- | ------------ | -------------------------- |
| LOW      | 自动执行         | 记录 Trace + Input/Output    |
| MEDIUM   | 自动执行 + 延迟回滚  | 记录 Input/Output + Snapshot |
| HIGH     | 预执行检查 + 异步通知 | 执行前后 Snapshot + 审计日志       |
| CRITICAL | 强制人工点击「批准」   | 全过程日志 + 操作者签名 + 多因素认证      |

**增强点**：

- CRITICAL 操作支持事务回滚和沙箱预演
- 审计日志加密存储，访问控制严格
- 多项目隔离：数据库、缓存、Token 完全独立

---

## 五、Orchestrator 核心逻辑 (增强版)

```python
class Orchestrator:
    def handle_request(self, user_input, project_id, context=None):
        try:
            # 1. 意图识别 (限定项目 + 多轮上下文)
            intent_info = self.router.get_intent(user_input, project_id, context)
            
            # 2. 组装 Prompt (继承 + 版本)
            final_prompt = self.prompt_manager.build(
                base="global_core_v2",
                domain=intent_info.domain,
                task=intent_info.prompt_ref,
                version=intent_info.version
            )

            # 3. 路由分支
            if intent_info.mode == "unified":
                return self.unified_agent.run(final_prompt, user_input)

            plan = self.planner.generate_plan(final_prompt, user_input)

            if self.security_gate.needs_approval(plan, intent_info.risk_level):
                self.security_gate.request_human_approval(plan)
                return "WAITING_FOR_APPROVAL"

            return self.executor.execute(plan)
        except ExternalAPIError as e:
            self.logger.error(f"API调用失败: {e}")
            return "API_ERROR"
        except Exception as e:
            self.logger.error(f"系统异常: {e}")
            return "SYSTEM_ERROR"
```

**增强点**：

- 异常处理与自动告警
- 多轮上下文传递
- Prompt 版本管理绑定
- 安全与审计接口集成

---

## 六、多项目隔离与安全增强

1. **环境隔离**：不同项目分配独立 API Key、Docker 容器、数据库实例。
2. **访问控制**：审计日志加密 + 访问权限严格控制。
3. **操作安全**：CRITICAL 任务支持多因素认证 + 沙箱预演 + 事务回滚。
4. **资源隔离**：限流策略 + 项目级缓存分离。

---

## 七、落地建议与工具推荐

1. **版本控制**：Git + Semantic Versioning，支持回滚和热加载。
2. **调试与追踪**：LangSmith / Arize Phoenix + Trace ID 打点
3. **异常监控**：集成 Sentry / Prometheus 告警
4. **沙箱模拟**：Executor 在沙箱中预演高风险任务
5. **Prompt 回滚**：与 Orchestrator 绑定版本，实现稳定回退

---

## 八、增强后的模块结构建议

```text
Orchestrator Enhancements:
├── router/
│   ├── intent_classifier.py        # 支持多项目 + 多轮上下文
│   └── conflict_resolver.py        # 模糊匹配 & 冲突处理
├── prompt_manager/
│   ├── renderer.py                 # Jinja2 + 参数模板渲染
│   └── version_control.py          # Prompt 版本管理 & 回滚
├── executor/
│   ├── api_caller.py               # 支持限流 / 失败重试
│   ├── transaction_manager.py      # CRITICAL 任务事务保护
│   └── sandbox_simulator.py        # 高风险任务沙箱预演
├── security_gate/
│   ├── risk_evaluator.py           # 风险分级计算
│   ├── approval_workflow.py        # 审批流接口
│   └── audit_logger.py             # 日志 + Snapshot + 加密存储
```

---

**总结**：  基础上实现企业级落地：

- 异常可控、日志可审计、任务安全隔离
- Prompt 版本管理、回滚机制、动态热加载
- 高风险操作沙箱预演 + 多因素审批
- 多项目扩展、上下文多轮支持

