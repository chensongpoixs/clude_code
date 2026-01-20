# 19 | 贡献指南 (Contribution Guide)

> **Status (状态)**: Stable (稳定)  
> **Audience (读者)**: Contributors / Maintainers (贡献者/维护者)  
> **Goal (目标)**: 降低开发者参与项目的门槛，统一代码提交与协作流程。

---

## 1. 开发环境设置 (Setup)

```bash
# 1. 克隆代码
git clone https://github.com/your-repo/clude-code.git
cd clude-code

# 2. 安装开发依赖 (包含 lint/test 工具)
pip install -e ".[dev,ui,rag]"

# 3. 安装 pre-commit 钩子 (确保提交前自动检查)
pre-commit install
```

---

## 2. 代码开发规范 (Workflow)

所有提交必须遵循 [`docs/CODE_SPECIFICATION.md`](./CODE_SPECIFICATION.md)：
1.  **分块提交**: 一个 PR 只解决一个具体问题。
2.  **双语注释**: 所有新功能必须补齐中英双语注释。
3.  **单元测试**: 核心逻辑（解析、策略、补丁）必须附带测试用例。

---

## 3. 文档质量门禁 (Doc Quality)

本项目强制执行“双语注释校验”：
- **操作**: 在提交前运行 `python tools/check_docs_bilingual.py`。
- **要求**: 任何新增的非代码块行，若包含英文则必须紧随对应的中文注释。

---

## 4. 提交规范 (Git Commit)

推荐使用 [Conventional Commits](https://www.conventionalcommits.org/):
- `feat(rag): 增加基于树语法的分块策略`
- `fix(cli): 修复 TUI 历史搜索中的路径乱码问题`
- `docs(faq): 补充关于 llama.cpp 连接失败的排查方案`

---

## 5. 相关文档 (See Also)

- **代码工程规范 (Spec)**: [`docs/CODE_SPECIFICATION.md`](./CODE_SPECIFICATION.md)
- **工程路线图 (Roadmap)**: [`docs/16-development-plan.md`](./16-development-plan.md)

