# 11 | 安全与策略（可实现规格）(Security & Policy Spec)

> **Status (状态)**: Stable Spec (稳定规格，部分已落地)  
> **Audience (读者)**: Maintainers / Security Engineers (维护者/安全工程师)  
> **Goal (目标)**: 确保 Agent 在本地拥有强能力的同时，满足“最小权限 (Least Privilege)、默认安全 (Secure by Default)、可审计 (Auditable)”的原则。

---

## 1. 威胁模型 (Threat Model)

### 1.1 主要风险 (Risks)
- **越权访问 (Unauthorized Access)**: 读取 workspace 外文件、读取凭据目录。
- **越权执行 (Unauthorized Execution)**: 执行破坏性命令 (`rm -rf`)、网络外联。
- **数据泄露 (Data Leakage)**: 将敏感信息写入日志或提交到 Git。

### 1.2 安全边界 (Security Boundaries)
- **文件系统**: 严格限制在 Workspace 及其子目录。
- **网络**: 默认禁用 (Allowlist 机制)。
- **交互**: 危险操作必须经由 **Human-in-the-loop** (HITL) 确认。

---

## 2. 策略引擎实现 (Policy Engine Implementation)

> **当前实现 (Current Implementation)**: `src/clude_code/policy/`

### 2.1 工具级白名单 (Tool Allowlist)
通过 `PolicyConfig` 控制允许使用的工具集合。

```python
# config.py
class PolicyConfig(BaseModel):
    allowed_tools: Optional[List[str]] = None  # 白名单
    disallowed_tools: List[str] = []           # 黑名单
    confirm_write: bool = True                 # 写操作确认
    confirm_exec: bool = True                  # 执行操作确认
```

### 2.2 命令执行白名单 (Command Allowlist)
在 `src/clude_code/verification/detector.py` 中实现了命令前缀检查。

- **Safe（安全）**: `npm test`, `pytest`, `cargo check`
- **Risky（高风险）**: `curl`, `wget`, `rm`, `dd`

### 2.3 路径沙箱 (Path Sandbox)
所有文件操作工具 (`read_file`, `write_file`) 必须：
1. 解析为绝对路径。
2. 检查是否以 `workspace_root` 为前缀。
3. 拒绝 `..` 穿越。

---

## 3. 敏感信息防护 (Sensitive Data Protection)

### 3.1 环境变量隔离
- 运行时移除 `*_TOKEN`, `*_KEY`, `PASSWORD` 等敏感环境变量。
- 仅传递构建所需的最小集 (如 `PATH`, `HOME`)。

### 3.2 审计日志脱敏
- 在写入 `audit.jsonl` 前，对参数中的敏感 Pattern (如 AWS Key, Bearer Token) 进行 Mask 处理。

---

## 4. 业界对比 (Industry Comparison)

| 特性 | Clude Code | Aider | Claude Code | 优势/差距 |
| :--- | :--- | :--- | :--- | :--- |
| **沙箱机制** | ✅ 路径强校验 | ✅ 路径校验 | ✅ 路径校验 | 持平 |
| **命令白名单** | ✅ 前缀匹配 | ❌ 较宽松 | ✅ 强限制 | **Clude 更严谨** |
| **工具权限** | ✅ 配置级 Allowlist | ❌ 无 | ✅ Allowlist | 持平 |
| **网络控制** | ✅ 默认禁用 | ❓ | ✅ 默认禁用 | 持平 |

---

## 5. 相关文档 (See Also)

- **工具协议 (Tool Protocol)**: [`docs/02-tool-protocol.md`](./02-tool-protocol.md)
- **运行时与命令执行 (Runtime)**: [`docs/07-runtime-and-terminal.md`](./07-runtime-and-terminal.md)
- **审计与可观测 (Observability)**: [`docs/12-observability.md`](./12-observability.md)
