"""
Prompt Profile Registry - Prompt Profile 注册表加载器

目的：
- 按 `agent_design_v_1.0.md` 的 Prompt Profile 抽象，引入一个“Intent 与 Prompt 资产”的中间层。
- Intent 通过 `prompt_profile` 引用 profile；profile 再决定 system/user 等 stage 的 prompt 组合。

实现策略（MVP）：
- 复用现有 StagePrompts（三层 base/domain/task）机制，避免引入新的渲染引擎。
- 文件路径：.clude/registry/prompt_profiles.yaml（可选；不存在则返回空配置）
- 支持 mtime 热加载。
"""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Optional

import yaml
from pydantic import ValidationError

from clude_code.core.project_paths import ProjectPaths
from clude_code.orchestrator.registry.schema import PromptProfilesConfig, PromptProfileSpec

_logger = logging.getLogger(__name__)


class PromptProfileRegistry:
    _instances: dict[str, "PromptProfileRegistry"] = {}
    _lock = threading.Lock()

    def __new__(cls, workspace_root: str) -> "PromptProfileRegistry":
        key = str(Path(workspace_root).resolve())
        with cls._lock:
            if key not in cls._instances:
                inst = super().__new__(cls)
                inst._initialized = False
                cls._instances[key] = inst
            return cls._instances[key]

    def __init__(self, workspace_root: str) -> None:
        if getattr(self, "_initialized", False):
            return
        self._workspace_root = Path(workspace_root).resolve()
        self._paths = ProjectPaths(workspace_root)
        self._config_path = self._paths.registry_dir() / "prompt_profiles.yaml"
        self._config: Optional[PromptProfilesConfig] = None
        self._last_mtime: float = 0.0
        self._config_lock = threading.Lock()
        self._initialized = True

    def _load_config(self) -> PromptProfilesConfig:
        if not self._config_path.exists():
            return PromptProfilesConfig()
        try:
            text = self._config_path.read_text(encoding="utf-8")
            data = yaml.safe_load(text) or {}
            cfg = PromptProfilesConfig.model_validate(data)
            _logger.info(f"[PromptProfileRegistry] 加载成功: {len(cfg.prompt_profiles)} 个 profiles")
            return cfg
        except yaml.YAMLError as e:
            _logger.error(f"[PromptProfileRegistry] YAML 解析失败: {e}")
            return PromptProfilesConfig()
        except ValidationError as e:
            _logger.error(f"[PromptProfileRegistry] 配置校验失败: {e}")
            return PromptProfilesConfig()
        except Exception as e:
            _logger.error(f"[PromptProfileRegistry] 加载失败: {e}")
            return PromptProfilesConfig()

    def _check_reload(self) -> None:
        if not self._config_path.exists():
            if self._config is not None:
                with self._config_lock:
                    self._config = PromptProfilesConfig()
                    self._last_mtime = 0.0
            return
        try:
            m = os.path.getmtime(self._config_path)
            if m > self._last_mtime:
                with self._config_lock:
                    self._config = self._load_config()
                    self._last_mtime = m
        except OSError as e:
            _logger.warning(f"[PromptProfileRegistry] mtime 检测失败: {e}")

    def get_config(self, *, force_reload: bool = False) -> PromptProfilesConfig:
        if force_reload:
            with self._config_lock:
                self._config = self._load_config()
                self._last_mtime = os.path.getmtime(self._config_path) if self._config_path.exists() else 0.0
                return self._config
        if self._config is None:
            with self._config_lock:
                if self._config is None:
                    self._config = self._load_config()
                    self._last_mtime = os.path.getmtime(self._config_path) if self._config_path.exists() else 0.0
        self._check_reload()
        return self._config  # type: ignore[return-value]

    def get_profile(self, name: str) -> Optional[PromptProfileSpec]:
        name = (name or "").strip()
        if not name:
            return None
        cfg = self.get_config()
        return cfg.prompt_profiles.get(name)

    @property
    def config_path(self) -> Path:
        return self._config_path


