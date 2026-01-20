# 08 | 自动化校验与闭环自愈（可实现规格）(Lint, Test & Build Spec)

> **Status (状态)**: Stable Spec (稳定规格，可直接落地实现)  
> **Audience (读者)**: Maintainers / Verification Owners (维护者/验证负责人)  
> **Goal (目标)**: 定义 Agent 如何集成 Lint/Test/Build（质量门禁/Quality Gates）形成闭环自愈（Self-Healing/自愈），把产出从“看似正确”提升到“工程正确”。

---

## 1. 质量门禁 (Quality Gates)

在任务进入 `SUMMARIZING` 阶段前，必须经过以下校验：

| 校验级别 | 工具示例 | 目的 |
| :--- | :--- | :--- |
| **L0: 静态分析** | `eslint`, `ruff`, `pyright`, `go vet` | 发现语法错误、未定义变量及拼写问题 |
| **L1: 构建校验** | `npm run build`, `make`, `cargo check` | 确保模块间接口协议与类型定义的一致性 |
| **L2: 功能测试** | `jest`, `pytest`, `go test` | 验证业务逻辑是否符合预期，防止回归错误 |

---

## 2. 闭环自愈机制 (Self-Healing)

当校验工具报错时，Agent 自动进入 `RECOVERING` 循环：
1. **解析错误**: 从 `stderr` 中精准提取文件名与行号。
2. **读取现场**: 自动对报错位置进行 `read_file`。
3. **修复尝试**: 模型分析错误堆栈，生成修复 Patch。
4. **再次验证**: 重新运行失败的校验项，直到通过或达到最大尝试次数（默认 3 次）。

---

## 3. 性能优化 (Optimization)

- **局部验证**: 优先运行与修改文件“强相关”的测试集（基于目录邻近度或 Git 变更关联）。
- **并行校验**: 在不冲突的前提下，同时启动 Lint 与类型检查。
- **缓存感知**: 尊重项目的构建缓存（如 `.next/cache`, `.pytest_cache`），避免重复计算。

---

---

## 4. 相关文档（See Also / 参见）

- **运行时与命令执行（Runtime & Terminal）**: [`docs/07-runtime-and-terminal.md`](./07-runtime-and-terminal.md)
- **代码编辑与补丁系统（Patching）**: [`docs/06-code-editing-and-patching.md`](./06-code-editing-and-patching.md)
- **自愈闭环实现报告（Verification）**: [`src/clude_code/verification/ANALYSIS_REPORT.md`](../src/clude_code/verification/ANALYSIS_REPORT.md)

---

## 5. 结论 (Conclusion/结论)

“没有自检的 Agent 产出代码不可靠”。通过将 Lint、Test 与 Build 深度集成到编排循环中，我们赋予了 Agent 独立发现并修复错误的能力，显著降低了开发者的 Code Review 负担。
