# Phase 1：Intent Registry Prompt 版本切换链路（可运营闭环）——实现思路

> 日期：2026-01-22  
> 目标：把“Prompt 三层继承 + SemVer + 回滚指针”与 Intent Registry 对齐，形成**可运营**的版本切换链路：不改代码即可切换/回滚 prompt 版本，并支持按意图区分不同提示词。

---

## 1. 需求与边界

### 1.1 核心诉求
- **registry schema**：需要能表达“按阶段(stage)选择提示词”，且每个 stage 都支持三层继承（base/domain/task）+ 指定版本。
- **示例与文档**：`.clude/registry/intents.example.yaml` 与 `docs/INTENT_REGISTRY.md` 需要与新 schema 对齐，给出可复制的配置模板。
- **加载逻辑**：加载器要支持 mtime 热加载；并能对旧字段做兼容映射（如历史存在 `prompt_ref/prompt_version`）。
- **版本切换闭环**：通过 `.clude/registry/prompt_versions.json` 的 `current -> previous` 指针实现“运营切换/回滚”，无需修改 `intents.yaml`。

### 1.2 非目标（本阶段不做）
- 不实现复杂的 SemVer 范围解析（例如 `^1.2` / `~1.2`），只支持**精确版本**。
- 不实现 UI 上的版本灰度/AB 流量分配（后续可在 registry 增加 weight/rollout 字段）。

---

## 2. 数据模型（Schema）设计

### 2.1 关键结构：按阶段的 PromptStage（三层）

定义一个 stage 的三层引用：
- `base.ref + base.version`
- `domain.ref + domain.version`
- `task.ref + task.version`

> 说明：version 可省略；省略时由 PromptManager 使用 `prompt_versions.json` 的 current 指针（若存在）自动选择。

### 2.2 Project 级默认 vs Intent 级覆盖

优先级：
1. `IntentSpec.prompts.{stage}`（意图级覆盖）
2. `ProjectConfig.prompts.{stage}`（项目级默认）
3. 代码内置默认（兜底）

### 2.3 旧字段兼容映射

为了避免历史配置直接失效：
- 如果 IntentSpec 存在旧字段 `prompt_ref/prompt_version`，则自动映射为：
  - `IntentSpec.prompts.planning.task.ref = prompt_ref`
  - `IntentSpec.prompts.planning.task.version = prompt_version`

---

## 3. 版本切换/回滚链路（Ops Playbook）

### 3.1 配置层（intents.yaml）
- 指定“用哪个提示词文件”（ref），以及可选指定“固定版本”（version）。

### 3.2 运营层（prompt_versions.json）
- 当 `intents.yaml` 未指定 version 时，PromptManager 将读取：
  - `prompt_versions.json.prompts[ref].current` 作为版本
  - 切换 current 时自动记录 previous（用于回滚）

### 3.3 热加载
- `IntentRegistry` 对 `intents.yaml` 做 mtime 热加载。
- `prompt_versions.json` 由 PromptManager 按需读取（改完即可生效，不依赖重启）。

---

## 4. 代码集成点

### 4.1 AgentLoop 的 prompt 选择
- system / planning / execute_step / replan / retry / classifier 等 stage：
  - 从 `IntentMatch` 获取 intent
  - 合并 project 默认 + intent 覆盖得到 stage prompt 三层 ref/version
  - 调用 `PromptManager.compose()` 生成最终 prompt 文本

### 4.2 execution/planning/classifier 的统一渲染方式
- 统一通过 `loop.prompt_manager.compose()` 渲染 stage prompt
- 仅当某 stage 未配置且代码默认也缺失时，返回一个最小兜底字符串（避免崩溃）

---

## 5. 验收点（Acceptance Criteria）
- 修改 `.clude/registry/intents.yaml` 的 prompts 配置后无需重启即可生效（mtime 热加载）。
- 修改 `.clude/registry/prompt_versions.json` 的 current 版本后无需重启即可切换 prompt 版本。
- 允许对同一 stage 按 intent 做不同 task prompt（例如 `planning_default` vs `planning_code_review`）。
- 所有调用点均不再依赖旧的 prompt_ref 字段；但旧字段存在时不会崩溃，并会被映射到 planning.task。


