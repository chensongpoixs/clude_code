"""
Prompt Profile Registry - 配置中心

功能：
1. 加载 prompt_profiles.yaml 配置
2. 按名称查找 Profile
3. 组合渲染 System Prompt
4. 获取 User Prompt 模板路径

对齐 agent_design_v_1.0.md 设计规范：
- Prompt Profile 是 Intent 与 Prompt 资产之间的唯一中间抽象层
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

from clude_code.prompts import read_prompt, render_prompt


# ============================================================
# 数据模型
# ============================================================

class RiskLevel(str, Enum):
    """风险等级"""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class PromptRef:
    """Prompt 引用"""
    ref: str  # 相对路径
    version: str = ""  # 版本号（可选）


@dataclass
class SystemPromptRefs:
    """System Prompt 引用（三层/四层模型）"""
    base: PromptRef | None = None  # Core 层（对应 system/core/）
    domain: PromptRef | None = None  # Role 层（对应 system/role/）
    task: PromptRef | None = None  # Context 层（对应 system/context/）
    policy: PromptRef | None = None  # Policy 层（对应 system/policy/）


@dataclass
class UserPromptRefs:
    """User Prompt 引用"""
    task: PromptRef | None = None


@dataclass
class PromptRefs:
    """Prompt 引用集合"""
    system: SystemPromptRefs = field(default_factory=SystemPromptRefs)
    user_prompt: UserPromptRefs = field(default_factory=UserPromptRefs)


@dataclass
class PromptProfile:
    """
    Prompt Profile - Intent 与 Prompt 资产的中间抽象层
    
    职责：
    - 决定 Agent 行为边界
    - 控制风险与权限
    - 组合 Prompt 资产
    """
    name: str
    description: str = ""
    risk_level: RiskLevel = RiskLevel.MEDIUM
    prompts: PromptRefs = field(default_factory=PromptRefs)
    
    def get_system_prompt(self, **context_vars: object) -> str:
        """
        组合渲染 System Prompt。
        
        参数:
            **context_vars: Context 层模板变量（如 tools_section, project_memory）
        
        返回:
            组合后的 System Prompt 文本
        """
        parts = []
        
        # 1. Core/Base 层（必选）
        if self.prompts.system.base:
            parts.append(read_prompt(
                self.prompts.system.base.ref,
                version=self.prompts.system.base.version or None,
            ))
        
        # 2. Role/Domain 层（可选）
        if self.prompts.system.domain:
            parts.append(read_prompt(
                self.prompts.system.domain.ref,
                version=self.prompts.system.domain.version or None,
            ))
        
        # 3. Policy 层（可选）
        if self.prompts.system.policy:
            parts.append(read_prompt(
                self.prompts.system.policy.ref,
                version=self.prompts.system.policy.version or None,
            ))
        
        # 4. Context/Task 层（可选，支持变量渲染）
        if self.prompts.system.task:
            ref = self.prompts.system.task.ref
            ver = self.prompts.system.task.version or None
            if ref.endswith(".j2"):
                parts.append(render_prompt(ref, version=ver, **context_vars))
            else:
                parts.append(read_prompt(ref, version=ver))
        
        return "\n\n".join(parts)
    
    def get_user_prompt_template(self) -> str | None:
        """获取 User Prompt 模板路径"""
        if self.prompts.user_prompt.task:
            return self.prompts.user_prompt.task.ref
        return None
    
    def render_user_prompt(self, **variables: object) -> str:
        """
        渲染 User Prompt。
        
        参数:
            **variables: 模板变量
        
        返回:
            渲染后的 User Prompt 文本
        """
        template = self.get_user_prompt_template()
        if not template:
            raise ValueError(f"Profile '{self.name}' has no user_prompt template")
        
        version = None
        if self.prompts.user_prompt.task:
            version = self.prompts.user_prompt.task.version or None
        
        return render_prompt(template, version=version, **variables)


# ============================================================
# 配置解析
# ============================================================

def _parse_prompt_ref(data: dict[str, Any] | None) -> PromptRef | None:
    """解析 PromptRef"""
    if not data:
        return None
    return PromptRef(
        ref=data.get("ref", ""),
        version=data.get("version", ""),
    )


def _parse_profile(name: str, data: dict[str, Any]) -> PromptProfile:
    """解析单个 Profile"""
    prompts_data = data.get("prompts", {})
    system_data = prompts_data.get("system", {})
    user_data = prompts_data.get("user_prompt", {})
    
    return PromptProfile(
        name=data.get("name", name),
        description=data.get("description", ""),
        risk_level=RiskLevel(data.get("risk_level", "MEDIUM")),
        prompts=PromptRefs(
            system=SystemPromptRefs(
                base=_parse_prompt_ref(system_data.get("base")),
                domain=_parse_prompt_ref(system_data.get("domain")),
                task=_parse_prompt_ref(system_data.get("task")),
                policy=_parse_prompt_ref(system_data.get("policy")),
            ),
            user_prompt=UserPromptRefs(
                task=_parse_prompt_ref(user_data.get("task")),
            ),
        ),
    )


# ============================================================
# Profile Registry
# ============================================================

class ProfileRegistry:
    """
    Prompt Profile 注册表
    
    功能：
    - 加载配置文件
    - 按名称查找 Profile
    - 列出所有 Profile
    """
    
    def __init__(self, config_path: str | Path | None = None):
        """
        初始化 Registry。
        
        参数:
            config_path: 配置文件路径，None = 使用默认路径
        """
        self._profiles: dict[str, PromptProfile] = {}
        self._config_path: Path | None = None
        self._loaded = False
        
        if config_path:
            self.load(config_path)
    
    def load(self, config_path: str | Path) -> None:
        """加载配置文件"""
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"Profile config not found: {config_path}")
        
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        
        profiles_data = data.get("prompt_profiles", {})
        for name, profile_data in profiles_data.items():
            self._profiles[name] = _parse_profile(name, profile_data)
        
        self._config_path = path
        self._loaded = True
    
    def get(self, name: str) -> PromptProfile | None:
        """按名称获取 Profile"""
        return self._profiles.get(name)
    
    def get_or_raise(self, name: str) -> PromptProfile:
        """按名称获取 Profile，不存在则抛异常"""
        profile = self.get(name)
        if not profile:
            raise KeyError(f"Profile not found: {name}")
        return profile
    
    def list_profiles(self) -> list[str]:
        """列出所有 Profile 名称"""
        return list(self._profiles.keys())
    
    def get_by_intent(self, intent_name: str) -> PromptProfile | None:
        """
        根据意图名称获取默认 Profile。
        
        约定：classifier_<intent_name> 为默认 Profile
        """
        # 尝试精确匹配
        profile_name = f"classifier_{intent_name.lower()}"
        profile = self.get(profile_name)
        if profile:
            return profile
        
        # 尝试模糊匹配（移除前缀）
        for name, p in self._profiles.items():
            if name.lower().endswith(intent_name.lower()):
                return p
        
        return None
    
    @property
    def is_loaded(self) -> bool:
        """是否已加载配置"""
        return self._loaded
    
    def __len__(self) -> int:
        return len(self._profiles)
    
    def __contains__(self, name: str) -> bool:
        return name in self._profiles


# ============================================================
# 单例与便捷函数
# ============================================================

_default_registry: ProfileRegistry | None = None


def get_default_registry(workspace_root: str | Path | None = None) -> ProfileRegistry:
    """
    获取默认 Registry（单例）。
    
    会自动尝试从以下路径加载配置：
    1. {workspace_root}/.clude/registry/prompt_profiles.yaml
    2. {workspace_root}/.clude/registry/prompt_profiles.example.yaml
    """
    global _default_registry
    
    if _default_registry is not None and _default_registry.is_loaded:
        return _default_registry
    
    _default_registry = ProfileRegistry()
    
    if workspace_root:
        root = Path(workspace_root)
        candidates = [
            root / ".clude" / "registry" / "prompt_profiles.yaml",
            root / ".clude" / "registry" / "prompt_profiles.example.yaml",
        ]
        for path in candidates:
            if path.exists():
                _default_registry.load(path)
                break
    
    return _default_registry


def reset_default_registry() -> None:
    """重置默认 Registry（用于测试）"""
    global _default_registry
    _default_registry = None

