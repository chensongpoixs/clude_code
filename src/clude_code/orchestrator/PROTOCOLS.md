# Orchestrator 核心协议与数据模型规范 (Protocols)

本规范定义了模块化开发中 Agent 内部交互的标准数据结构。

---

## 1. 显式规划协议 (Planning Schema)

用于解决 L1 (Manager) 编排任务。

### 1.1 `Plan` 对象
```json
{
  "title": "任务全局目标",
  "steps": [
    {
      "id": "step_1",
      "description": "分析 src/auth.py 中的登录逻辑",
      "dependencies": [],
      "status": "pending",
      "tools_expected": ["read_file", "grep"]
    },
    {
      "id": "step_2",
      "description": "修改 session 过期时间配置",
      "dependencies": ["step_1"],
      "status": "pending",
      "tools_expected": ["apply_patch"]
    }
  ],
  "verification_policy": "run_pytest"
}
```

---

## 2. 验证闭环协议 (Verification Schema)

用于 P0 优先级的“自修复”反馈。

### 2.1 `VerificationResult` 对象
```json
{
  "ok": false,
  "type": "test_failure",
  "summary": "3 tests failed, 12 passed",
  "details": [
    {
      "file": "tests/test_auth.py",
      "line": 45,
      "error": "AssertionError: expected 3600 but got 1800",
      "context": "def test_session_expiry():\n > assert config.EXPIRY == 3600"
    }
  ],
  "suggestion": "Check the config.py default value."
}
```

---

## 3. 提示词增强策略 (Prompt Engineering)

为了强制模型进行显式规划，必须在 `SYSTEM_PROMPT` 中增加以下“状态强制”约束：

### 3.1 规划阶段强制模板
当 Agent 处于 `PLANNING` 状态时，强制其输出以下格式：
> **[PLAN]**
> 1. [ ] 步骤 A (工具: ...)
> 2. [ ] 步骤 B (工具: ...)
> ...

---

## 4. 异常与熔断策略 (Circuit Breaker)

| 场景 | 处理策略 | 动作 |
| :--- | :--- | :--- |
| **Token 溢出** | 强制执行 `_trim_history` | 截断最久远的 user/assistant 对，保留 system |
| **重复调用 (Stuttering)** | 计数器 > 50 | 注入 `E_STUTTERING` 错误并强制模型切换思路 |
| **循环死锁** | 迭代次数 > 20 | 返回 `AgentTurn(stop_reason="MAX_ITER")` 并提示用户人工干预 |
| **工具超时** | `timeout_s` 触发 | 杀掉子进程，返回 `E_TIMEOUT` |

---

## 5. 模块化落地目录建议 (Updated)

```bash
src/clude_code/
├── orchestrator/      # 核心编排
│   ├── planner.py     # [待实现] L1 规划逻辑
│   ├── state_m.py     # [待实现] 显式状态机 (Enum)
│   ├── agent_loop.py  # L2 执行循环
│   └── protocols.md   # 本规范文档
├── verification/      # [待实现] 验证闭环
│   ├── detector.py    # 项目类型自动探测
│   └── runner.py      # pytest/eslint 统一运行器
└── context/
    └── retriever.py   # [待实现] 多源检索融合入口
```

