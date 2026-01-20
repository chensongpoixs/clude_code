# 14 | 插件生态系统（可实现规格）(Plugin Ecosystem Spec)

> **Status (状态)**: Experimental (实验性)  
> **Audience (读者)**: Plugin Developers (插件开发者)  
> **Goal (目标)**: 定义如何通过插件（Plugins）扩展 Agent 的 UI、工具集与核心逻辑，实现生态的解耦。

---

## 1. 插件架构 (Plugin Architecture)

### 1.1 核心原则 (Principles)
- **非侵入式 (Non-intrusive)**: 插件不应修改 Core 代码，而是通过 Hook 或 Registry 注入。
- **动态加载 (Dynamic Loading)**: 支持在运行时或启动时扫描加载插件。

### 1.2 插件类型 (Types)
1.  **UI Plugins**: 替换或增强 CLI/TUI 界面 (如 `opencode_tui`, `enhanced_live_view`)。
2.  **Tool Plugins**: 提供新的工具 (如 `database_query`, `jira_ticket`)。
3.  **Policy Plugins**: 提供自定义的安全策略 (如企业级 DLP)。

---

## 2. 插件实现 (Implementation)

> **当前实现**: `src/clude_code/plugins/`

### 2.1 UI 插件示例
UI 插件本质上是 `ChatHandler` 的不同实现或扩展。

```python
# src/clude_code/plugins/ui/__init__.py
from .enhanced_chat_handler import EnhancedChatHandler
from .opencode_tui import run_opencode_tui
```

通过 `--live-ui` 参数动态选择：
```bash
clude chat --live-ui opencode
```

### 2.2 自定义命令 (Custom Commands)
用户可以在 `.clude/commands/*.md` 中定义简单的 Prompt 别名插件。

```markdown
---
name: review
description: Review current changes
---
请审查当前的 git diff，并给出改进建议。
```

---

## 3. 路线图 (Roadmap)

- [ ] **Phase 1**: UI 插件化 (已完成)。
- [ ] **Phase 2**: 工具热插拔 (基于 Python Entry Points)。
- [ ] **Phase 3**: 插件市场/Registry。

---

## 4. 相关文档 (See Also)

- **UI 与 UX (UI/UX)**: [`docs/13-ui-cli-ux.md`](./13-ui-cli-ux.md)
- **工具协议 (Tool Protocol)**: [`docs/02-tool-protocol.md`](./02-tool-protocol.md)
