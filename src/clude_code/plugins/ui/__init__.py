"""
UI 插件（实验性）

目的：
- 承载非核心/可选 UI 实现（例如增强版 Live UI），避免 `cli/` 主链路膨胀
- 保持 `ChatHandler` 单入口，UI 仅作为“渲染器”被选择

说明：
- 当前 UI 插件是“内置插件形态”的代码组织方式（仍随仓库发布）
- 未来可扩展为真正的外部插件加载（例如从 `.clude/plugins/` 加载 manifest）
"""

__all__ = [
    "enhanced_live_view",
    "enhanced_chat_handler",
]
