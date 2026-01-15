"""
配置管理器
支持用户偏好的持久化存储和管理
"""
import json
from pathlib import Path
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field

from clude_code.config import CludeConfig


class UIConfig(BaseModel):
    """UI 用户偏好配置"""
    theme: str = Field(default="default", description="主题：default, dark, light")
    color_scheme: str = Field(default="vibrant", description="配色方案：vibrant, minimal, high_contrast")
    refresh_rate: int = Field(default=12, ge=1, le=60, description="Live 界面刷新率（Hz）")
    show_animations: bool = Field(default=True, description="是否显示动画效果")
    show_icons: bool = Field(default=True, description="是否显示状态图标")
    compact_mode: bool = Field(default=False, description="紧凑模式（减少空行）")
    layout: str = Field(default="default", description="布局模式：default, split, grid")

    # 快捷键配置（键: 功能名）
    shortcuts: Dict[str, str] = Field(default_factory=dict, description="自定义快捷键映射")


class EditorConfig(BaseModel):
    """编辑器相关配置"""
    preferred_editor: str = Field(default="auto", description="首选编辑器：auto, vim, nano, vscode")
    line_numbers: bool = Field(default=True, description="是否显示行号")
    syntax_highlighting: bool = Field(default=True, description="是否启用语法高亮")
    auto_save: bool = Field(default=True, description="是否自动保存")
    tab_size: int = Field(default=4, ge=2, le=8, description="制表符大小")


class HistoryConfig(BaseModel):
    """历史记录配置"""
    max_history_size: int = Field(default=1000, ge=100, le=10000, description="最大历史记录数")
    history_file: str = Field(default="~/.clude/history.json", description="历史记录文件路径")
    save_history: bool = Field(default=True, description="是否保存历史记录")
    search_enabled: bool = Field(default=True, description="是否启用历史搜索")


class ExtendedCludeConfig(CludeConfig):
    """扩展的配置类，包含UI和其他用户偏好"""

    # 新增配置
    ui: UIConfig = Field(default_factory=UIConfig)
    editor: EditorConfig = Field(default_factory=EditorConfig)
    history: HistoryConfig = Field(default_factory=HistoryConfig)


class ConfigManager:
    """配置管理器，负责配置的加载、保存和运行时更新"""

    def __init__(self, config_path: Optional[str] = None):
        """初始化配置管理器

        Args:
            config_path: 配置文件路径，如果为None则使用默认路径
        """
        self.config_path = Path(config_path) if config_path else self._get_default_config_path()
        self.config = self._load_config()

    def _get_default_config_path(self) -> Path:
        """获取默认配置文件路径"""
        return Path.home() / ".clude" / "config.json"

    def _load_config(self) -> ExtendedCludeConfig:
        """加载配置文件"""
        try:
            if self.config_path.exists():
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return ExtendedCludeConfig(**data)
            else:
                # 创建默认配置
                config = ExtendedCludeConfig()
                # 先尝试保存，如果失败则静默跳过
                try:
                    self._save_config(config)
                except Exception:
                    pass  # 保存失败时不影响程序运行
                return config
        except Exception as e:
            print(f"警告：加载配置文件失败，使用默认配置: {e}")
            return ExtendedCludeConfig()

    def _save_config(self, config: ExtendedCludeConfig) -> None:
        """保存配置到文件"""
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, 'w', encoding='utf-8') as f:
                # 使用自定义编码器处理Path对象等
                data = config.model_dump()
                json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        except Exception as e:
            print(f"警告：保存配置文件失败: {e}")

    def save_config(self) -> None:
        """保存当前配置"""
        self._save_config(self.config)

    def reload_config(self) -> None:
        """重新加载配置"""
        self.config = self._load_config()

    def get_config(self) -> ExtendedCludeConfig:
        """获取当前配置"""
        return self.config

    def update_config(self, key_path: str, value: Any) -> None:
        """更新配置项（支持嵌套路径）

        Args:
            key_path: 配置路径，如 "ui.theme" 或 "llm.model"
            value: 新值
        """
        try:
            keys = key_path.split('.')
            obj = self.config

            # 遍历到倒数第二级
            for key in keys[:-1]:
                if hasattr(obj, key):
                    obj = getattr(obj, key)
                else:
                    raise ValueError(f"配置路径不存在: {'.'.join(keys[:keys.index(key)+1])}")

            # 设置最终值
            if hasattr(obj, keys[-1]):
                setattr(obj, keys[-1], value)
                self.save_config()
            else:
                raise ValueError(f"配置项不存在: {key_path}")

        except Exception as e:
            raise ValueError(f"更新配置失败: {e}")

    def get_config_value(self, key_path: str) -> Any:
        """获取配置值（支持嵌套路径）

        Args:
            key_path: 配置路径，如 "ui.theme" 或 "llm.model"

        Returns:
            配置值
        """
        try:
            keys = key_path.split('.')
            obj = self.config

            for key in keys:
                if hasattr(obj, key):
                    obj = getattr(obj, key)
                else:
                    raise ValueError(f"配置路径不存在: {key_path}")

            return obj

        except Exception as e:
            raise ValueError(f"获取配置失败: {e}")

    def reset_to_defaults(self) -> None:
        """重置为默认配置"""
        self.config = ExtendedCludeConfig()
        self.save_config()

    def export_config(self, export_path: Optional[str] = None) -> str:
        """导出配置到文件

        Args:
            export_path: 导出路径，如果为None则返回JSON字符串

        Returns:
            如果export_path为None，返回JSON字符串，否则返回文件路径
        """
        data = self.config.model_dump()

        if export_path:
            export_file = Path(export_path)
            export_file.parent.mkdir(parents=True, exist_ok=True)
            with open(export_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False, default=str)
            return str(export_file)
        else:
            return json.dumps(data, indent=2, ensure_ascii=False, default=str)

    def import_config(self, import_path: str) -> None:
        """从文件导入配置

        Args:
            import_path: 导入文件路径
        """
        import_file = Path(import_path)
        if not import_file.exists():
            raise FileNotFoundError(f"配置文件不存在: {import_path}")

        with open(import_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        try:
            self.config = ExtendedCludeConfig(**data)
            self.save_config()
        except Exception as e:
            raise ValueError(f"导入配置失败，配置格式错误: {e}")

    def validate_config(self) -> bool:
        """验证当前配置是否有效

        Returns:
            True if valid, False otherwise
        """
        try:
            # 尝试创建配置对象来验证
            ExtendedCludeConfig(**self.config.model_dump())
            return True
        except Exception:
            return False

    def get_config_summary(self) -> Dict[str, Any]:
        """获取配置摘要"""
        return {
            "config_file": str(self.config_path),
            "config_valid": self.validate_config(),
            "ui_theme": self.config.ui.theme,
            "animations_enabled": self.config.ui.show_animations,
            "compact_mode": self.config.ui.compact_mode,
            "model": self.config.llm.model,
            "workspace": self.config.workspace_root,
        }


# 全局配置管理器实例
_config_manager: Optional[ConfigManager] = None

def get_config_manager() -> ConfigManager:
    """获取全局配置管理器实例"""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager

def init_config_manager(config_path: Optional[str] = None) -> ConfigManager:
    """初始化配置管理器"""
    global _config_manager
    _config_manager = ConfigManager(config_path)
    return _config_manager