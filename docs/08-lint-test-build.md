# 08｜质量闭环：Lint / Test / Build（Verification Loop）

目标：把“验证”变成一等公民，形成自动修复闭环，减少“改完但跑不起来”的情况。

## 1. 子模块拆分

### 1.1 Detector（项目类型探测）
- **输入**：文件树、常见配置文件
- **输出**：`ProjectProfile`
  - 语言与框架（node/python/go/java/…）
  - 包管理器（npm/pnpm/yarn/pip/poetry/go mod/…）
  - 测试框架（jest/pytest/go test/…）
  - 可能的命令集合

### 1.2 Verifier（验证器）
- **职责**：根据策略运行 lint/test/build
- **输入**：`VerificationPolicy` + `ProjectProfile`
- **输出**：`VerificationResult`

### 1.3 AutoFixer（自动修复器，可选）
- **职责**：对可自动修复的 lint/format 问题执行 `--fix`
- **策略**：
  - 先 `format` 再 `lint --fix`
  - 修复后重新验证一次（避免引入新问题）

## 2. 数据结构

### 2.1 ProjectProfile
- `stack: string[]`
- `commands: { lint?: string[], test?: string[], build?: string[] }`
- `default_verify_order: ("lint"|"test"|"build")[]`

### 2.2 VerificationResult
- `ok: boolean`
- `stage: lint|test|build|custom`
- `exit_code: number`
- `summary: string`
- `issues: Issue[]`（可选结构化）

### 2.3 Issue（建议）
- `type: lint|test|build`
- `path?: string`
- `line?: number`
- `rule?: string`
- `message: string`

## 3. 执行策略

### 3.1 默认顺序（可配置）
- 前端：lint → test → build
- 后端：test → lint → build（按团队习惯）

### 3.2 快速验证（Fast Path）
- 小改动默认只跑 lint 或受影响测试（需要符号/依赖图支持）

### 3.3 失败闭环
- 验证失败 → 解析错误 → 生成修复步骤 → 应用 patch → 再验证
- 连续失败超过阈值（如 3 次）停止自动修复，输出手工建议

## 4. MVP 实现建议
- 先做：从常见配置推断命令（package.json / pyproject / go.mod）
- 再做：结构化解析（提取文件与行号）
- 最后做：增量测试/影响分析（依赖图）


