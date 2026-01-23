## skill（`src/clude_code/tooling/tools/skill.py`）业界优化点

### 当前模块职责

- 加载工作区中的“技能” Markdown（`load_skill`），并列出技能（`list_skills`）。

### 业界技术原理

- **明确的技能目录与命名空间**：业界通常把技能放在固定目录（例如 `.clude/skills/`），避免把整个仓库的 `*.md` 都当成技能。
- **元数据解析应使用标准 YAML**：front matter 通常是 YAML 而不是 JSON；用 JSON 解析会导致兼容性差。
- **输出预算**：技能内容可能很长，应提供 `max_chars` 或只返回摘要 + 路径。

### 现状评估（本项目）

- `load_skill` 读取 `{skill_name}.md`，并尝试把 front matter 当 JSON 解析（兼容性偏弱）。
- `list_skills` 会 rglob 所有 `*.md`（范围过大，易噪音）。

### 可优化点（建议优先级）

- **P0：收敛技能目录**
  - **建议**：默认只扫描 `.clude/skills/**/*.md`，并提供配置扩展路径。

- **P1：YAML front matter 支持**
  - **建议**：用 `yaml.safe_load`（可选依赖）解析；缺依赖时回退“只返回正文不解析元数据”。


