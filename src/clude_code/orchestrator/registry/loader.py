"""
Intent Registry Loader - 意图注册表加载器

功能：
- 从 .clude/registry/intents.yaml 加载项目意图配置
- 支持 mtime 热加载（检测文件变更自动重载）
- 线程安全的单例模式
"""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Optional

import yaml
from pydantic import ValidationError

from clude_code.orchestrator.registry.schema import ProjectConfig, IntentSpec
from clude_code.core.project_paths import ProjectPaths


_logger = logging.getLogger(__name__)


class IntentRegistry:
    """
    意图注册表管理器。
    
    负责加载、缓存和热更新意图配置。
    支持全局注册表（.clude/registry/intents.yaml）。
    
    使用示例：
        registry = IntentRegistry(workspace_root)
        config = registry.get_config()
        intent = config.get_intent_by_name("code_review")
    """
    
    # 单例实例缓存：workspace_root -> IntentRegistry
    _instances: dict[str, "IntentRegistry"] = {}
    _lock = threading.Lock()
    
    def __new__(cls, workspace_root: str) -> "IntentRegistry":
        """单例模式：每个 workspace_root 共享一个实例。"""
        key = str(Path(workspace_root).resolve())
        with cls._lock:
            if key not in cls._instances:
                instance = super().__new__(cls)
                instance._initialized = False
                cls._instances[key] = instance
            return cls._instances[key]
    
    def __init__(self, workspace_root: str) -> None:
        if getattr(self, "_initialized", False):
            return
        
        self._workspace_root = Path(workspace_root).resolve()
        self._paths = ProjectPaths(workspace_root)
        self._config_path = self._paths.intents_file()
        
        self._config: Optional[ProjectConfig] = None
        self._last_mtime: float = 0.0
        self._config_lock = threading.Lock()
        
        self._initialized = True
        _logger.debug(f"[IntentRegistry] 初始化完成: {self._config_path}")
    
    def _load_config(self) -> ProjectConfig:
        """从 YAML 文件加载配置。"""
        if not self._config_path.exists():
            _logger.debug(f"[IntentRegistry] 配置文件不存在，使用空配置: {self._config_path}")
            return ProjectConfig()
        
        try:
            text = self._config_path.read_text(encoding="utf-8")
            data = yaml.safe_load(text) or {}
            config = ProjectConfig.model_validate(data).normalize()
            _logger.info(f"[IntentRegistry] 加载配置成功: {len(config.intents)} 个意图")
            return config
        except yaml.YAMLError as e:
            _logger.error(f"[IntentRegistry] YAML 解析失败: {e}")
            return ProjectConfig()
        except ValidationError as e:
            _logger.error(f"[IntentRegistry] 配置校验失败: {e}")
            return ProjectConfig()
        except Exception as e:
            _logger.error(f"[IntentRegistry] 加载配置失败: {e}")
            return ProjectConfig()
    
    def _check_reload(self) -> None:
        """检测文件变更并重载（mtime 热加载）。"""
        if not self._config_path.exists():
            if self._config is not None:
                _logger.info("[IntentRegistry] 配置文件已删除，重置为空配置")
                with self._config_lock:
                    self._config = ProjectConfig()
                    self._last_mtime = 0.0
            return
        
        try:
            current_mtime = os.path.getmtime(self._config_path)
            if current_mtime > self._last_mtime:
                _logger.info(f"[IntentRegistry] 检测到配置变更，重新加载")
                with self._config_lock:
                    self._config = self._load_config()
                    self._last_mtime = current_mtime
        except OSError as e:
            _logger.warning(f"[IntentRegistry] 检测文件变更失败: {e}")
    
    def get_config(self, *, force_reload: bool = False) -> ProjectConfig:
        """
        获取当前配置（支持热加载）。
        
        Args:
            force_reload: 是否强制重载
            
        Returns:
            ProjectConfig 实例
        """
        if force_reload:
            with self._config_lock:
                self._config = self._load_config()
                if self._config_path.exists():
                    self._last_mtime = os.path.getmtime(self._config_path)
                return self._config
        
        # 首次加载
        if self._config is None:
            with self._config_lock:
                if self._config is None:
                    self._config = self._load_config()
                    if self._config_path.exists():
                        self._last_mtime = os.path.getmtime(self._config_path)
        
        # 热加载检测
        self._check_reload()
        
        return self._config  # type: ignore[return-value]
    
    def get_intent(self, name: str) -> Optional[IntentSpec]:
        """根据名称获取意图配置。"""
        config = self.get_config()
        return config.get_intent_by_name(name)
    
    def list_intents(self, *, enabled_only: bool = True) -> list[IntentSpec]:
        """列出所有意图。"""
        config = self.get_config()
        if enabled_only:
            return [i for i in config.intents if i.enabled]
        return list(config.intents)
    
    @property
    def config_path(self) -> Path:
        """配置文件路径。"""
        return self._config_path
    
    @classmethod
    def clear_instances(cls) -> None:
        """清除所有单例实例（用于测试）。"""
        with cls._lock:
            cls._instances.clear()

