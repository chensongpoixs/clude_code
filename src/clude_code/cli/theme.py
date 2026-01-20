"""
统一的 UI 主题和样式定义
符合 Clude Code 的配色方案，适配中文界面
"""
from rich.theme import Theme
from rich.style import Style
from rich.text import Text
from typing import Dict, Any


# Clude Code 风格配色方案
CLAUDE_THEME = Theme({
    "success": "bold green",
    "warning": "bold yellow",
    "error": "bold red",
    "info": "bold cyan",
    "dim": "grey70",
    "highlight": "bold white",
    "path": "italic cyan",
    "code": "on black",
    "user_input": "bold blue",
    "assistant": "bold magenta",
    "tool": "yellow",

    # 组件特定颜色
    "orchestrator": "bold cyan",
    "planner": "bold magenta",
    "context": "bold blue",
    "llm": "bold green",
    "fs": "yellow",
    "shell": "bold white",
    "git": "bold red",
    "verify": "bold green",

    # 状态颜色
    "running": "bold yellow",
    "done": "bold green",
    "error": "bold red",
    "pending": "grey70",
    "idle": "grey70",

    # 中文界面友好样式
    "title": "bold white on blue",
    "subtitle": "bold cyan",
    "section": "bold yellow",
    "prompt": "bold green",
    "panel_border": "blue",
    "success_border": "green",
    "warning_border": "yellow",
    "error_border": "red",
})

# 状态徽章样式
STATUS_STYLES = {
    "RUNNING": Style(color="yellow", bold=True),
    "DONE": Style(color="green", bold=True),
    "ERROR": Style(color="red", bold=True),
    "PENDING": Style(color="grey70"),
}

# 标题样式
TITLE_STYLE = "bold white on blue"
SUBTITLE_STYLE = "bold cyan"
SECTION_STYLE = "bold yellow"

# 提示符样式
PROMPT_STYLE = "bold green"

# 面板样式
PANEL_STYLES = {
    "default": "blue",
    "success": "green",
    "warning": "yellow",
    "error": "red",
    "info": "cyan",
}

# 图标系统（支持动画）
class StatusIcons:
    """状态图标，支持动画效果"""

    # 静态图标
    PENDING = "⏳"
    RUNNING = "🔄"
    SUCCESS = "✅"
    ERROR = "❌"
    WARNING = "⚠️"
    INFO = "ℹ️"

    # 组件图标
    COMPONENTS = {
        "orchestrator": "🧠",
        "planner": "📋",
        "context": "📖",
        "llm": "🤖",
        "fs": "📁",
        "shell": "💻",
        "git": "🔀",
        "verify": "✔️",
    }

    # 动画图标序列
    LOADING_SPINNER = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    PROGRESS_BAR_CHARS = "░▒▓█"
    FADE_CHARS = "░▒▓█"

    @classmethod
    def get_loading_icon(cls, frame: int) -> str:
        """获取加载动画图标"""
        return cls.LOADING_SPINNER[frame % len(cls.LOADING_SPINNER)]

    @classmethod
    def get_progress_bar(cls, progress: float, width: int = 20) -> str:
        """生成进度条字符串"""
        filled = int(progress * width)
        empty = width - filled
        return f"[cyan]{cls.PROGRESS_BAR_CHARS[-1] * filled}[/cyan][dim]{cls.PROGRESS_BAR_CHARS[0] * empty}[/dim]"

class ColorTheme:
    """颜色主题配置"""

    # 基础颜色
    PRIMARY = "cyan"
    SUCCESS = "green"
    WARNING = "yellow"
    ERROR = "red"
    INFO = "blue"
    DIM = "dim"

    # 组件颜色映射
    COMPONENT_COLORS = {
        "orchestrator": "bold cyan",
        "planner": "bold magenta",
        "context": "bold blue",
        "llm": "bold green",
        "fs": "yellow",
        "shell": "bold white",
        "git": "bold red",
        "verify": "bold green",
    }

    # 状态颜色映射
    STATUS_COLORS = {
        "idle": "dim",
        "running": "bold yellow",
        "done": "bold green",
        "error": "bold red",
        "pending": "dim",
    }

    @classmethod
    def get_component_style(cls, component: str) -> str:
        """获取组件样式"""
        return cls.COMPONENT_COLORS.get(component, cls.PRIMARY)

    @classmethod
    def get_status_style(cls, status: str) -> str:
        """获取状态样式"""
        return cls.STATUS_COLORS.get(status.lower(), cls.DIM)

def create_welcome_text() -> Text:
    """创建欢迎横幅文本"""
    welcome = Text()
    welcome.append("✨ ", style="bold yellow")
    welcome.append("Clude Code", style="bold white")
    welcome.append(" - 本地编程代理 CLI", style="dim")
    return welcome

def create_status_bar(cfg: Any) -> Text:
    """创建状态栏文本"""
    status = Text()

    # 版本信息
    status.append(f"版本: {getattr(cfg, '__version__', '0.1.0')}  ", style="dim")

    # 模型信息
    model = getattr(cfg.llm, 'model', '未配置')
    status.append(f"模型: {model[:20]}  ", style="dim")

    # 工作区信息
    workspace = getattr(cfg, 'workspace_root', '.')
    status.append(f"工作区: {workspace}", style="dim")

    return status

def create_ready_message() -> Text:
    """创建就绪消息"""
    ready = Text()
    ready.append("✓ 已就绪！输入查询或输入 ", style="green")
    ready.append("exit", style="yellow")
    ready.append(" 退出", style="green")
    return ready