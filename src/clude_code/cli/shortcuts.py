"""
快捷键处理系统
支持基础和高级快捷键，包含命令历史和自动补全
"""
import threading
import time
from typing import Dict, List, Optional, Callable, Any, Tuple
from enum import Enum
from dataclasses import dataclass
from rich.console import Console
from rich.prompt import Prompt
from rich.text import Text
from rich.panel import Panel


class ShortcutAction(Enum):
    """快捷键动作类型"""
    EXIT = "exit"
    CLEAR = "clear"
    HELP = "help"
    CONFIG = "config"
    HISTORY = "history"
    SAVE = "save"
    LOAD = "load"
    DEBUG = "debug"
    REFRESH = "refresh"
    PREVIOUS_COMMAND = "previous_command"
    NEXT_COMMAND = "next_command"
    AUTO_COMPLETE = "auto_complete"
    SHOW_STATUS = "show_status"
    TOGGLE_DEBUG = "toggle_debug"
    CUSTOM = "custom"


@dataclass
class ShortcutDefinition:
    """快捷键定义"""
    key: str
    action: ShortcutAction
    description: str
    category: str = "general"
    enabled: bool = True


class CommandHistory:
    """命令历史管理器"""

    def __init__(self, max_size: int = 1000):
        self.history: List[str] = []
        self.max_size = max_size
        self.current_index = -1

    def add_command(self, command: str) -> None:
        """添加命令到历史"""
        if command.strip() and (not self.history or self.history[-1] != command):
            self.history.append(command)
            if len(self.history) > self.max_size:
                self.history.pop(0)
        self.current_index = len(self.history)

    def get_previous(self) -> Optional[str]:
        """获取上一条命令"""
        if self.history and self.current_index > 0:
            self.current_index -= 1
            return self.history[self.current_index]
        return None

    def get_next(self) -> Optional[str]:
        """获取下一条命令"""
        if self.history and self.current_index < len(self.history) - 1:
            self.current_index += 1
            return self.history[self.current_index]
        elif self.current_index == len(self.history) - 1:
            self.current_index = len(self.history)
            return ""
        return None

    def search_history(self, query: str, limit: int = 10) -> List[str]:
        """搜索历史命令"""
        matches = []
        for cmd in reversed(self.history):
            if query.lower() in cmd.lower():
                matches.append(cmd)
                if len(matches) >= limit:
                    break
        return matches

    def clear_history(self) -> None:
        """清空历史"""
        self.history.clear()
        self.current_index = -1

    def get_recent_commands(self, limit: int = 10) -> List[str]:
        """获取最近的命令"""
        return self.history[-limit:] if self.history else []


class AutoCompleter:
    """自动补全器"""

    def __init__(self):
        self.commands = [
            "/help", "/clear", "/exit", "/config", "/history",
            "/save", "/load", "/debug", "/refresh", "/status"
        ]
        self.slash_commands = [
            "/help", "/clear", "/exit", "/config", "/history",
            "/save", "/load", "/debug", "/refresh", "/status"
        ]

    def get_completions(self, prefix: str) -> List[str]:
        """获取补全建议"""
        if not prefix:
            return []

        completions = []
        for cmd in self.commands:
            if cmd.startswith(prefix):
                completions.append(cmd)

        return completions[:10]  # 最多返回10个建议

    def get_slash_completions(self, prefix: str) -> List[str]:
        """获取斜杠命令补全"""
        if not prefix.startswith('/'):
            return []

        return [cmd for cmd in self.slash_commands if cmd.startswith(prefix)]


class ShortcutHandler:
    """快捷键处理器"""

    # 默认快捷键映射
    DEFAULT_SHORTCUTS = {
        # 基础快捷键
        "ctrl+c": ShortcutDefinition("Ctrl+C", ShortcutAction.EXIT, "退出程序"),
        "ctrl+d": ShortcutDefinition("Ctrl+D", ShortcutAction.EXIT, "退出程序"),
        "ctrl+l": ShortcutDefinition("Ctrl+L", ShortcutAction.CLEAR, "清屏"),
        "f1": ShortcutDefinition("F1", ShortcutAction.HELP, "显示帮助"),
        "f2": ShortcutDefinition("F2", ShortcutAction.CONFIG, "显示配置"),

        # 历史导航
        "up": ShortcutDefinition("↑", ShortcutAction.PREVIOUS_COMMAND, "上一条命令"),
        "down": ShortcutDefinition("↓", ShortcutAction.NEXT_COMMAND, "下一条命令"),
        "ctrl+r": ShortcutDefinition("Ctrl+R", ShortcutAction.REFRESH, "刷新界面"),

        # 高级功能
        "f5": ShortcutDefinition("F5", ShortcutAction.REFRESH, "刷新/重新加载"),
        "f3": ShortcutDefinition("F3", ShortcutAction.SHOW_STATUS, "显示状态"),
        "f4": ShortcutDefinition("F4", ShortcutAction.TOGGLE_DEBUG, "切换调试模式"),
    }

    def __init__(self, console: Console):
        self.console = console
        self.shortcuts = self.DEFAULT_SHORTCUTS.copy()
        self.history = CommandHistory()
        self.autocompleter = AutoCompleter()
        self.custom_actions: Dict[str, Callable] = {}

        # 快捷键状态
        self.enabled = True
        self.current_input = ""
        self.input_position = 0

    def register_shortcut(self, key: str, action: ShortcutAction,
                         description: str, category: str = "custom") -> None:
        """注册自定义快捷键"""
        self.shortcuts[key] = ShortcutDefinition(key, action, description, category)

    def register_custom_action(self, action_name: str, callback: Callable) -> None:
        """注册自定义动作"""
        self.custom_actions[action_name] = callback

    def enable_shortcuts(self) -> None:
        """启用快捷键"""
        self.enabled = True

    def disable_shortcuts(self) -> None:
        """禁用快捷键"""
        self.enabled = False

    def prompt_with_shortcuts(self, prompt_text: str = "you",
                            default: str = "") -> 'PromptResult':
        """带快捷键支持的提示输入

        Returns:
            PromptResult: 包含输入文本和可能的快捷键动作
        """
        return EnhancedPrompt.ask(
            prompt_text,
            console=self.console,
            shortcuts=self.shortcuts,
            history=self.history,
            autocompleter=self.autocompleter,
            default=default
        )

    def execute_shortcut_action(self, action: ShortcutAction, **kwargs) -> Any:
        """执行快捷键动作"""
        if action == ShortcutAction.EXIT:
            return self._handle_exit()
        elif action == ShortcutAction.CLEAR:
            return self._handle_clear()
        elif action == ShortcutAction.HELP:
            return self._handle_help()
        elif action == ShortcutAction.CONFIG:
            return self._handle_config()
        elif action == ShortcutAction.HISTORY:
            return self._handle_history()
        elif action == ShortcutAction.SAVE:
            return self._handle_save(**kwargs)
        elif action == ShortcutAction.LOAD:
            return self._handle_load(**kwargs)
        elif action == ShortcutAction.DEBUG:
            return self._handle_debug()
        elif action == ShortcutAction.REFRESH:
            return self._handle_refresh()
        elif action == ShortcutAction.CUSTOM:
            return self._handle_custom(**kwargs)

        return None

    def _handle_exit(self) -> str:
        """处理退出"""
        self.console.print("\n[bold yellow]再见！[/bold yellow]")
        return "exit"

    def _handle_clear(self) -> str:
        """处理清屏"""
        self.console.clear()
        return "clear"

    def _handle_help(self) -> str:
        """处理帮助"""
        self._show_help_panel()
        return "help"

    def _handle_config(self) -> str:
        """处理配置显示"""
        self._show_config_panel()
        return "config"

    def _handle_history(self) -> str:
        """处理历史记录"""
        self._show_history_panel()
        return "history"

    def _handle_save(self, **kwargs) -> str:
        """处理保存"""
        name = kwargs.get('name', 'session')
        self.console.print(f"[green]会话已保存: {name}[/green]")
        return f"save:{name}"

    def _handle_load(self, **kwargs) -> str:
        """处理加载"""
        name = kwargs.get('name', 'session')
        self.console.print(f"[green]会话已加载: {name}[/green]")
        return f"load:{name}"

    def _handle_debug(self) -> str:
        """处理调试切换"""
        self.console.print("[yellow]调试模式已切换[/yellow]")
        return "debug"

    def _handle_refresh(self) -> str:
        """处理刷新"""
        self.console.print("[cyan]界面已刷新[/cyan]")
        return "refresh"

    def _handle_custom(self, **kwargs) -> Any:
        """处理自定义动作"""
        action_name = kwargs.get('action_name')
        if action_name and action_name in self.custom_actions:
            return self.custom_actions[action_name](**kwargs)
        return None

    def _show_help_panel(self) -> None:
        """显示帮助面板"""
        from rich.table import Table
        from rich.panel import Panel

        table = Table(title="可用快捷键", show_header=True)
        table.add_column("快捷键", style="cyan", width=12)
        table.add_column("功能", style="white")
        table.add_column("分类", style="yellow", width=10)

        for key, shortcut in self.shortcuts.items():
            if shortcut.enabled:
                table.add_row(key, shortcut.description, shortcut.category)

        panel = Panel(
            table,
            title="帮助信息",
            border_style="blue",
            padding=(1, 2)
        )

        self.console.print(panel)
        self.console.print()

    def _show_config_panel(self) -> None:
        """显示配置面板"""
        from clude_code.config import get_config_manager

        config_manager = get_config_manager()
        summary = config_manager.get_config_summary()

        from rich.table import Table
        from rich.panel import Panel

        table = Table(title="当前配置", show_header=False)
        table.add_column("配置项", style="cyan", width=20)
        table.add_column("值", style="white")

        for key, value in summary.items():
            table.add_row(key.replace('_', ' ').title(), str(value))

        panel = Panel(
            table,
            title="配置信息",
            border_style="green",
            padding=(1, 2)
        )

        self.console.print(panel)
        self.console.print()

    def _show_history_panel(self) -> None:
        """显示历史记录面板"""
        recent_commands = self.history.get_recent_commands(10)

        if not recent_commands:
            self.console.print("[dim]暂无历史记录[/dim]")
            return

        from rich.table import Table
        from rich.panel import Panel

        table = Table(title="最近命令", show_header=False)
        table.add_column("#", style="cyan", width=3, justify="right")
        table.add_column("命令", style="white")

        for i, cmd in enumerate(reversed(recent_commands), 1):
            table.add_row(str(i), cmd)

        panel = Panel(
            table,
            title="命令历史",
            border_style="magenta",
            padding=(1, 2)
        )

        self.console.print(panel)
        self.console.print()


class PromptResult:
    """提示输入结果"""

    def __init__(self, text: str, action: Optional[ShortcutAction] = None,
                 action_data: Optional[Dict[str, Any]] = None):
        self.text = text
        self.action = action
        self.action_data = action_data or {}


class EnhancedPrompt:
    """增强的提示输入，支持快捷键和历史"""

    @staticmethod
    def ask(prompt_text: str, console: Console,
            shortcuts: Dict[str, ShortcutDefinition],
            history: CommandHistory,
            autocompleter: AutoCompleter,
            default: str = "") -> PromptResult:
        """带增强功能的提示输入"""

        # 显示提示符
        prompt_display = f"[bold cyan]{prompt_text}[/bold cyan]"
        if default:
            prompt_display += f" [dim](默认: {default})[/dim]"

        # 简单的实现（实际项目中需要更复杂的按键处理）
        try:
            user_input = Prompt.ask(prompt_display, default=default)

            # 处理斜杠命令
            if user_input.startswith('/'):
                return EnhancedPrompt._handle_slash_command(user_input)

            # 添加到历史
            history.add_command(user_input)

            return PromptResult(text=user_input)

        except KeyboardInterrupt:
            # Ctrl+C 被捕获
            return PromptResult(text="", action=ShortcutAction.EXIT)
        except EOFError:
            # Ctrl+D 被捕获
            return PromptResult(text="", action=ShortcutAction.EXIT)

    @staticmethod
    def _handle_slash_command(command: str) -> PromptResult:
        """处理斜杠命令"""
        cmd = command.strip().lower()

        if cmd == "/exit" or cmd == "/quit":
            return PromptResult(text="", action=ShortcutAction.EXIT)
        elif cmd == "/clear":
            return PromptResult(text="", action=ShortcutAction.CLEAR)
        elif cmd == "/help":
            return PromptResult(text="", action=ShortcutAction.HELP)
        elif cmd == "/config":
            return PromptResult(text="", action=ShortcutAction.CONFIG)
        elif cmd == "/history":
            return PromptResult(text="", action=ShortcutAction.HISTORY)
        elif cmd == "/debug":
            return PromptResult(text="", action=ShortcutAction.DEBUG)
        elif cmd == "/refresh":
            return PromptResult(text="", action=ShortcutAction.REFRESH)
        elif cmd.startswith("/save "):
            name = cmd[6:].strip()
            return PromptResult(text="", action=ShortcutAction.SAVE,
                              action_data={"name": name})
        elif cmd.startswith("/load "):
            name = cmd[6:].strip()
            return PromptResult(text="", action=ShortcutAction.LOAD,
                              action_data={"name": name})

        # 未知斜杠命令，当作普通输入
        return PromptResult(text=command)