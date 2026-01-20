"""
动画效果实现
提供打字机效果、淡入淡出、加载动画等重度动画支持
"""
import time
import threading
from typing import List, Callable, Optional, Any
from rich.console import Console
from rich.text import Text
from rich.live import Live
from rich.panel import Panel

from clude_code.cli.theme import create_welcome_text, create_status_bar, create_ready_message


class AnimationBase:
    """动画基类"""

    def __init__(self, console: Console):
        self.console = console
        self.running = False
        self.thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """启动动画"""
        self.running = True
        self.thread = threading.Thread(target=self._animate, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        """停止动画"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)

    def _animate(self) -> None:
        """动画主循环（子类实现）"""
        raise NotImplementedError


class LoadingSpinner(AnimationBase):
    """加载旋转动画"""

    def __init__(self, console: Console, message: str = "加载中..."):
        super().__init__(console)
        self.message = message
        self.spinner_chars = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self.current_frame = 0

    def _animate(self) -> None:
        """旋转动画实现"""
        while self.running:
            spinner = self.spinner_chars[self.current_frame % len(self.spinner_chars)]
            self.console.print(f"\r{spinner} {self.message}", end="")
            self.current_frame += 1
            time.sleep(0.1)


class TypewriterEffect(AnimationBase):
    """打字机效果"""

    def __init__(self, console: Console, text: str, delay: float = 0.05):
        super().__init__(console)
        self.full_text = text
        self.delay = delay
        self.current_text = ""
        self.on_update: Optional[Callable[[str], None]] = None

    def set_update_callback(self, callback: Callable[[str], None]) -> None:
        """设置更新回调"""
        self.on_update = callback

    def _animate(self) -> None:
        """打字机动画实现"""
        for char in self.full_text:
            if not self.running:
                break
            self.current_text += char
            if self.on_update:
                self.on_update(self.current_text)
            time.sleep(self.delay)

        # 确保最终显示完整文本
        if self.on_update:
            self.on_update(self.full_text)


class FadeEffect:
    """淡入淡出效果"""

    @staticmethod
    def fade_in(console: Console, text: Text, duration: float = 0.5) -> None:
        """淡入效果"""
        frames = 5  # 减少帧数以避免重复
        delay = duration / frames

        for i in range(1, frames + 1):
            opacity = i / frames
            faded_text = text.copy()

            # 简单的不透明度模拟
            if opacity < 0.5:
                faded_text.stylize("dim")
            else:
                faded_text.stylize("white")

            console.print(faded_text, end="\r")
            time.sleep(delay)

        # 最终显示完整文本
        console.print(text)

    @staticmethod
    def fade_out(console: Console, text: Text, duration: float = 0.3) -> None:
        """淡出效果"""
        frames = 8
        delay = duration / frames

        for i in range(frames, -1, -1):
            opacity = i / frames
            faded_text = text.copy()

            if opacity < 0.3:
                faded_text.stylize("dim")
            elif opacity < 0.7:
                faded_text.stylize("white")
            else:
                faded_text.stylize("bold")

            console.print(faded_text, end="\r")
            time.sleep(delay)

        console.print()


class ProgressBarAnimation:
    """进度条动画"""

    def __init__(self, console: Console, width: int = 40):
        self.console = console
        self.width = width
        self.progress_chars = "░▒▓█"

    def render_progress(self, progress: float, label: str = "") -> str:
        """渲染进度条"""
        percentage = int(progress * 100)
        filled = int(progress * self.width)

        bar = ""
        for i in range(self.width):
            if i < filled:
                # 根据进度位置选择不同的填充字符
                char_index = min(3, int((i / self.width) * 4))
                bar += self.progress_chars[char_index]
            else:
                bar += self.progress_chars[0]

        return f"[cyan]{bar}[/cyan] {percentage:3d}% {label}"


class StatusIndicatorAnimation(AnimationBase):
    """状态指示器动画（闪烁效果）"""

    def __init__(self, console: Console, status_text: str, status_type: str = "running"):
        super().__init__(console)
        self.status_text = status_text
        self.status_type = status_type
        self.blink_states = [True, False]  # 闪烁状态
        self.current_blink = 0

    def _animate(self) -> None:
        """状态闪烁动画"""
        while self.running:
            visible = self.blink_states[self.current_blink % len(self.blink_states)]

            if visible:
                if self.status_type == "running":
                    self.console.print(f"🔄 {self.status_text}", end="\r")
                elif self.status_type == "error":
                    self.console.print(f"❌ {self.status_text}", end="\r")
                elif self.status_type == "success":
                    self.console.print(f"✅ {self.status_text}", end="\r")
                else:
                    self.console.print(f"⏳ {self.status_text}", end="\r")
            else:
                self.console.print(" " * (len(self.status_text) + 2), end="\r")

            self.current_blink += 1
            time.sleep(0.5)


class LiveTextAnimation:
    """实时文本更新动画"""

    def __init__(self, console: Console, initial_text: str = ""):
        self.console = console
        self.current_text = initial_text
        self.live: Optional[Live] = None
        self.panel = Panel(self.current_text, title="实时更新", border_style="blue")

    def start(self) -> None:
        """启动实时更新"""
        self.live = Live(self.panel, console=self.console, refresh_per_second=4)
        self.live.start()

    def update_text(self, new_text: str) -> None:
        """更新文本内容"""
        self.current_text = new_text
        if self.live:
            self.panel = Panel(self.current_text, title="实时更新", border_style="blue")
            self.live.update(self.panel)

    def stop(self) -> None:
        """停止实时更新"""
        if self.live:
            self.live.stop()


class AnimatedWelcome:
    """动画欢迎界面"""

    def __init__(self, console: Console):
        self.console = console

    def show_welcome(self, cfg: Any) -> None:
        """显示欢迎界面（稳定版，优先保证无重复显示）"""
        try:
            # 标题
            title_text = create_welcome_text()
            self.console.print(title_text)

            # 状态栏
            status_text = create_status_bar(cfg)
            self.console.print(status_text)
            self.console.print()

            # 分隔线
            self.console.print("─" * 60)

            # 就绪消息
            ready_text = create_ready_message()
            self.console.print(ready_text)
            self.console.print()  # 额外空行

        except Exception as e:
            # 降级到简单欢迎
            self.console.print("[bold cyan]Clude Code - 本地编程代理 CLI[/bold cyan]\n")
            self.console.print()
            self.console.print(f"版本: {getattr(cfg, '__version__', '0.1.0')}\n")
            self.console.print("\n")
            self.console.print(f"模型: {getattr(cfg.llm, 'model', '未配置')}\n")
            self.console.print("\n")
            self.console.print(f"工作区: {getattr(cfg, 'workspace_root', '.')}\n")
            self.console.print("\n")
            self.console.print("[green]✓ 已就绪！输入查询或输入 exit 退出[/green]")
            self.console.print()