# Phase 1：prompt_versions 路径纳入 ProjectPaths + prompts validate（可运营校验）——实现思路

> 日期：2026-01-22  
> 目标：把 prompt 版本指针文件纳入 `ProjectPaths` 并明确隔离策略；同时提供 `clude prompts validate` 做“ref/版本/front matter”一致性校验，避免线上运营切换时把系统弄挂。

---

## 1. prompt_versions.json 的路径与隔离策略

### 1.1 问题
目前 prompt 版本指针文件是通过代码直接拼接 `.clude/registry/prompt_versions.json`，没有在 `ProjectPaths` 里形成统一入口，且“全局共享/按 project 隔离”的策略不够明确。

### 1.2 策略选择（明确化）

我们支持两种策略，并在 `ProjectPaths` 里显式表达：

- **GLOBAL（默认）**：跨项目共享一份版本指针  
  路径：`{workspace_root}/.clude/registry/prompt_versions.json`  
  适用：企业运营统一管控 prompt 版本（同一套规则覆盖多个 project）。

- **PROJECT（可选）**：按 project 独立版本指针  
  路径：`{workspace_root}/.clude/projects/{project_id}/registry/prompt_versions.json`  
  适用：不同项目需要不同 prompt 版本灰度/回滚策略，互不干扰。

> 默认采用 GLOBAL，是因为：registry/intents.yaml 本身是全局共享目录（`.clude/registry`），多数情况下也希望 prompt 版本策略一致；而需要隔离时再显式切到 PROJECT。

### 1.3 行为约定（兼容性与可运营性）
- CLI `clude prompts ...` 默认操作 GLOBAL 文件；同时提供 `--scope global|project` 选择。
- PromptManager 读取版本指针时，同样按 scope 选择（当前实现保持默认 GLOBAL，以最小风险上线；后续可把 scope 放入配置/registry）。

---

## 2. clude prompts validate：校验范围与规则

### 2.1 为什么需要 validate
运营切换（pin/rollback）非常容易造成：
- ref 拼错/文件不存在
- 指定 version 但版本化文件不存在
- prompt 文件 front matter 语法错误、字段缺失、layer 非法
这些问题会在运行时才暴露（更糟糕会在 planning/replan 时崩），因此需要一个“上线前校验”命令。

### 2.2 validate 的输入集合（Refs 来源）
validate 需要收集全部 prompt refs（去重）：
- `.clude/registry/intents.yaml`（若存在）：project.prompts + intent.prompts 的所有 stage 的 base/domain/task refs
- `prompt_versions.json`：prompts 键集合（ref 列表）
- 命令行参数：`validate [ref]` 时只校验该 ref（可选同时带 version）

### 2.3 校验规则（最小但有效）
- **R1：ref 文件存在**  
  `src/clude_code/prompts/{ref}` 必须存在

- **R2：版本文件存在（当 version 被使用时）**  
  若 `intents.yaml` 或 `prompt_versions.json` 指定了 ref 的 current/previous/version：
  - 版本化文件名按规则推导：`foo/bar.j2 + 1.2.3 => foo/bar_v1.2.3.j2`
  - 必须存在，否则报错

- **R3：front matter 合规**（新工程强约束）
  - 文件必须包含 YAML front matter（顶部 `--- ... ---`）
  - 至少包含字段：`title`、`version`、`layer`
  - `layer` ∈ {`base`,`domain`,`task`}
  - 若指定 version，则 front matter 的 `version` 必须与该版本一致（防止 ref/version 指向错内容）

### 2.4 输出与退出码
- 输出：列出 error/warn 的条目（包含 ref、路径、原因）
- 若存在任何 error：退出码非 0（Typer 抛 `Exit(code=2)`）

---

## 3. render_prompt 的 front matter 剥离

由于新工程 prompt 都带 YAML front matter，直接 `render_prompt()` 会把 front matter 发给 LLM，影响模型输出稳定性。  
因此 `render_prompt()` 必须在渲染前自动剥离 front matter，仅渲染正文 body。

---

## 4. 验收点（Acceptance Criteria）
- `ProjectPaths` 提供 `prompt_versions_file(scope=...)`，CLI/PromptManager 不再手写路径拼接。
- `clude prompts validate`：
  - 能校验 intents.yaml + prompt_versions.json 引用的所有 ref
  - 能发现缺失文件/缺失版本文件/front matter 不合法
  - 输出清晰，错误时退出码非 0
- `render_prompt` 不再把 front matter 发给 LLM。


