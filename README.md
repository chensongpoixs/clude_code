# clude code（业界 Code Agent / Claude Code 类）模块化落地开发文档

本仓库当前用于沉淀一套“业界 Claude Code/Code Agent CLI”形态的**功能分析 + 核心模块拆解 + 可实现的模块化开发文档**（偏工程落地，不是概念介绍）。

## Day1 运行（Python 纯 CLI + llama.cpp HTTP）

详见：`docs/21-llama-cpp-http.md`

## 源码实现与进度报告 (src/)

详见：`src/README.md`，包含每个模块的详细分析、完成度百分比以及下一步任务清单。

### conda（Windows / PowerShell）

```powershell
conda create -n clude_code python=3.11 -y
conda activate clude_code
pip install -e .

$env:CLUDE_WORKSPACE_ROOT="D:\Work\AI\clude_code"
$env:CLUDE_LLM__BASE_URL="http://127.0.0.1:8080"
$env:CLUDE_LLM__API_MODE="openai_compat"   # 或 completion

clude doctor
clude chat
```

## 快速开始（阅读顺序）

1. 总览与范围：`docs/00-overview.md`
2. 端到端流程与状态机：`docs/01-e2e-flow-and-state-machine.md`
3. 工具协议（Tool/Function Calling）：`docs/02-tool-protocol.md`
4. 模块目录索引：`docs/99-module-index.md`

## 文档目录

- `docs/00-overview.md`：产品形态、目标、非目标、SLO、安全边界
- `docs/01-e2e-flow-and-state-machine.md`：交互流程、状态机、失败恢复
- `docs/02-tool-protocol.md`：工具协议、参数校验、返回规范、权限与沙箱
- `docs/03-repo-indexing.md`：仓库索引/检索（grep/语义检索/文件树）
- `docs/04-context-and-prompting.md`：上下文构建、提示词模板、会话策略
- `docs/05-planning-and-tasking.md`：计划/分解/执行控制（todo、回滚）
- `docs/06-code-editing-and-patching.md`：编辑策略、补丁格式、冲突处理
- `docs/07-runtime-and-terminal.md`：命令执行、后台任务、输出裁剪
- `docs/08-lint-test-build.md`：静态检查、测试与构建编排
- `docs/09-git-workflow.md`：diff、提交、分支、PR 生成（可选）
- `docs/10-memory-and-knowledge.md`：短期/长期记忆、隐私与生命周期
- `docs/11-security-and-policy.md`：权限、密钥、敏感信息、越权防护
- `docs/12-observability.md`：日志、指标、Tracing、回放与审计
- `docs/13-ui-cli-ux.md`：CLI/交互 UX、流式输出、确认机制
- `docs/14-plugin-ecosystem.md`：插件/工具扩展、版本与兼容
- `docs/15-deployment.md`：本地/企业私有化、配置、更新渠道
- `docs/99-module-index.md`：模块清单、依赖关系、接口总表


