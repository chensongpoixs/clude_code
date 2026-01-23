"""
Orchestrator Registry - 配置注册中心

包含：
- ProfileRegistry: Prompt Profile 注册表
- IntentRegistry: 意图注册表
"""

from .profile_registry import (
    ProfileRegistry,
    PromptProfile,
    PromptRefs,
    PromptRef,
    RiskLevel,
    get_default_registry,
    reset_default_registry,
)

from .intent_registry import (
    IntentRegistry,
    IntentCategory,
    IntentConfig,
    IntentMatch,
    get_default_intent_registry,
    reset_default_intent_registry,
    get_default_profile_for_category,
)

__all__ = [
    # Profile Registry
    "ProfileRegistry",
    "PromptProfile",
    "PromptRefs",
    "PromptRef",
    "RiskLevel",
    "get_default_registry",
    "reset_default_registry",
    # Intent Registry
    "IntentRegistry",
    "IntentCategory",
    "IntentConfig",
    "IntentMatch",
    "get_default_intent_registry",
    "reset_default_intent_registry",
    "get_default_profile_for_category",
]

