# Phase 4：审计加密与企业监控——实现思路（MVP）

> 日期：2026-01-22  
> 对齐：`docs/AGENT_DESIGN_ENTERPRISE_FEASIBILITY_REPORT.md` Phase 4（L180-L185）

---

## 1. 目标与验收

### 交付
- 审计加密（可选）：audit JSONL 支持加密落盘
- 脱敏：对审计事件中的敏感字段进行递归脱敏
- 导出报表：提供 CLI 导出审计摘要（便于合规/审计人员查看）
- 企业监控接入点：明确 Prometheus/Sentry/告警的挂载方式（MVP 先打接口与降级）

### 验收
- 合规可用：可审计、可导出、权限隔离明确
- 加密/脱敏开启时不泄露关键敏感信息（API Key/Token/Authorization/密码）
- 依赖缺失或 key 缺失不会让 Agent 崩溃（可配置 fail-closed）

---

## 2. 审计加密设计（可选）

### 2.1 加密粒度与文件格式
- 仍保持 **JSONL**（一行一条事件），但 `data`（或整行）可加密
- MVP 选择：**整行加密**（除了必要的最小索引字段），便于降低泄露面
- 输出建议结构：
  - `{"enc":"AESGCM","kid":"env:CLUDE_AUDIT_KEY","nonce":"...","ciphertext":"...","ts":...,"trace_id":...,"session_id":...,"project_id":...,"event":...}`

### 2.2 密钥来源与轮换
- key 从环境变量读取（例如 `CLUDE_AUDIT_AESGCM_KEY_B64`），配置只存 env 名
- 允许 `kid` 记录 key id（便于轮换与解密）
- MVP 不实现自动轮换，仅提供“换 key 后新日志用新 key”

### 2.3 依赖与降级
- AES‑GCM 推荐用 `cryptography`（可选依赖）
- 行为开关：
  - encrypt_enabled=false：明文 JSONL（现状）
  - encrypt_enabled=true 且依赖/key 缺失：
    - fail_closed=false：降级明文并写 warning（MVP 默认）
    - fail_closed=true：抛错并拒绝写入（更严格合规场景）

---

## 3. 脱敏设计（递归 + 文本模式）

### 3.1 递归脱敏（结构化 data）
- 对 dict/list 递归处理
- key 命中敏感名单时替换为 `******`
- 默认敏感 key：
  - `api_key`, `token`, `access_token`, `refresh_token`, `authorization`, `password`, `secret`, `cookie`, `set-cookie`

### 3.2 文本脱敏（如 user_message/assistant_text）
- 对字符串执行轻量正则替换：
  - `Bearer <...>`、`sk-...`、`AKIA...` 等常见模式（MVP 先覆盖常见）
- 注意：脱敏不应破坏可读性（保留前后少量字符）

---

## 4. 导出报表（MVP）

### 4.1 目标
- 不要求解密（如果开启加密，报表可只输出“计数/事件类型/时间范围”）
- 输出：
  - 总事件数、按 event 分类计数
  - 按 trace_id/session_id 聚合
  - 最近 N 条（可选脱敏/可选仅元数据）

### 4.2 CLI 形态（建议）
- `clude observability audit-export --project-id xxx --limit 200 --format json`
- format：`json` / `table`

---

## 5. 企业监控：接入点与降级

### 5.1 Prometheus
- 现状：已有 metrics + prometheus export（文件/输出）
- 下一步（非阻塞）：提供 HTTP endpoint 或导出到 node exporter textfile 目录

### 5.2 Sentry
- 接入点：AgentLoop 顶层异常、工具异常、LLM 调用失败
- MVP：仅在配置启用时初始化 SDK；缺依赖/DSN 不崩溃

### 5.3 告警规则（后续）
- 指标：LLM 超时率、工具错误率、审批积压、沙箱失败率


