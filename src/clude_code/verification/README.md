# 验证闭环（Verification / Self-healing Loop）

本模块提供 **自动验证 + 结构化报错回喂** 能力，用于在 Agent 改代码后自动运行测试/构建，并将失败信息结构化回注给下一轮 LLM，从而形成“失败→修复”的自愈闭环。

---

## 1. 入口与职责

- **项目探测**：`detector.py`（`ProjectDetector.detect()`）
  - 识别项目类型（python/nodejs/go/rust）
  - 选择合适的验证命令
  - 命令白名单：`ProjectDetector.is_safe_command()`
- **验证执行**：`runner.py`（`Verifier.run_verify()`）
  - 执行验证命令（捕获 stdout/stderr，避免破坏 Live UI）
  - 环境隔离：剔除敏感环境变量（token/secret/password）
  - 结构化解析：将输出解析为 `VerificationResult`

---

## 2. 优点（当前实现）

- **安全性增强**：命令白名单 + 敏感环境变量剔除
- **可观测性**：全量原始输出写入日志（file-only logger）
- **健壮性**：
  - 可配置超时
  - 编码容错（`utf-8` + `errors=replace`）
  - 针对 `shell=True` 的“命令不可用”启发式识别
  - 多语言正则解析（Python/Node.js/Go/Rust）

---

## 3. 局限与后续（Backlog）

- **`shell=True`**：短期可用但长期建议迁移到 `shell=False` + 参数数组（Windows 兼容需要额外处理）
- **重试/并行**：尚未实现 flaky test 重试与 lint/test 并行
- **解析准确率**：当前以正则为主，未来可针对 pytest/jest 输出做更强结构化解析

---

## 4. 文档

- **详细优缺点与健壮性报告**：`ANALYSIS_REPORT.md`
- **阶段 2 实现报告**：`IMPLEMENTATION_REPORT_PHASE2.md`


