"""
Intent Registry - 意图注册与路由

功能：
1. 加载 intents.yaml 配置
2. 关键词匹配意图
3. Intent → Profile 映射
4. project_id 级覆盖

对齐 agent_design_v_1.0.md 设计规范：
- Intent 通过 prompt_profile 引用 Profile，Profile 决定 prompt 组合
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

from .profile_registry import RiskLevel, ProfileRegistry


# ============================================================
# 完整意图分类（11类）
# ============================================================

class IntentCategory(str, Enum):
    """
    用户意图分类标签（完整版）
    
    对齐 agent_design_v_1.0.md 和 user/stage/intent_classify.j2
    """
    # 核心功能类
    CODING_TASK = "CODING_TASK"                 # 代码编写、修改、重构、测试
    ERROR_DIAGNOSIS = "ERROR_DIAGNOSIS"         # 错误分析、调试、问题定位
    REPO_ANALYSIS = "REPO_ANALYSIS"             # 代码分析、架构理解、入口查找
    DOCUMENTATION_TASK = "DOCUMENTATION_TASK"   # 文档生成、注释、README
    
    # 咨询与规划类
    TECHNICAL_CONSULTING = "TECHNICAL_CONSULTING"  # 技术咨询、概念解释、最佳实践
    PROJECT_DESIGN = "PROJECT_DESIGN"           # 架构设计、技术选型
    SECURITY_CONSULTING = "SECURITY_CONSULTING" # 安全咨询、漏洞分析
    
    # 元交互类
    CAPABILITY_QUERY = "CAPABILITY_QUERY"       # 能力询问、使用方法
    GENERAL_CHAT = "GENERAL_CHAT"               # 问候、寒暄
    CASUAL_CHAT = "CASUAL_CHAT"                 # 开放式闲聊
    
    # 兜底类
    UNCERTAIN = "UNCERTAIN"                     # 意图模糊


# ============================================================
# 数据模型
# ============================================================

@dataclass
class IntentConfig:
    """意图配置"""
    name: str
    description: str = ""
    keywords: list[str] = field(default_factory=list)
    mode: str = "unified"  # unified | split
    risk_level: RiskLevel = RiskLevel.MEDIUM
    prompt_profile: str = ""  # 关联的 Profile 名称
    tools: list[str] = field(default_factory=list)
    priority: int = 0
    project_overrides: dict[str, str] = field(default_factory=dict)  # project_id -> profile


@dataclass
class IntentMatch:
    """意图匹配结果"""
    intent: IntentConfig
    score: float  # 匹配分数（0-1）
    matched_keywords: list[str]


# ============================================================
# 意图映射（Category → 默认 Profile）
# ============================================================

_CATEGORY_TO_DEFAULT_PROFILE: dict[IntentCategory, str] = {
    IntentCategory.CODING_TASK: "classifier_coding_task",
    IntentCategory.ERROR_DIAGNOSIS: "classifier_error_diagnosis",
    IntentCategory.REPO_ANALYSIS: "classifier_repo_analysis",
    IntentCategory.DOCUMENTATION_TASK: "classifier_documentation_task",
    IntentCategory.TECHNICAL_CONSULTING: "classifier_technical_consulting",
    IntentCategory.PROJECT_DESIGN: "classifier_project_design",
    IntentCategory.SECURITY_CONSULTING: "classifier_security_consulting",
    IntentCategory.CAPABILITY_QUERY: "classifier_capability_query",
    IntentCategory.GENERAL_CHAT: "classifier_general_chat",
    IntentCategory.CASUAL_CHAT: "classifier_casual_chat",
    IntentCategory.UNCERTAIN: "classifier_uncertain",
}


def get_default_profile_for_category(category: IntentCategory) -> str:
    """获取意图分类对应的默认 Profile 名称"""
    return _CATEGORY_TO_DEFAULT_PROFILE.get(category, "classifier_uncertain")


# ============================================================
# Intent Registry
# ============================================================

class IntentRegistry:
    """
    意图注册表
    
    功能：
    - 加载配置文件
    - 关键词匹配意图
    - Intent → Profile 映射
    """
    
    def __init__(self, config_path: str | Path | None = None):
        """
        初始化 Registry。
        
        参数:
            config_path: 配置文件路径，None = 不加载
        """
        self._intents: dict[str, IntentConfig] = {}
        self._config_path: Path | None = None
        self._loaded = False
        self._default_risk_level = RiskLevel.MEDIUM
        self._default_mode = "unified"
        
        if config_path:
            self.load(config_path)
    
    def load(self, config_path: str | Path) -> None:
        """加载配置文件"""
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"Intent config not found: {config_path}")
        
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        
        self._default_risk_level = RiskLevel(data.get("default_risk_level", "MEDIUM"))
        self._default_mode = data.get("default_mode", "unified")
        
        intents_data = data.get("intents", [])
        for intent_data in intents_data:
            name = intent_data.get("name", "")
            if not name:
                continue
            
            self._intents[name] = IntentConfig(
                name=name,
                description=intent_data.get("description", ""),
                keywords=intent_data.get("keywords", []),
                mode=intent_data.get("mode", self._default_mode),
                risk_level=RiskLevel(intent_data.get("risk_level", self._default_risk_level.value)),
                prompt_profile=intent_data.get("prompt_profile", ""),
                tools=intent_data.get("tools", []),
                priority=intent_data.get("priority", 0),
                project_overrides=intent_data.get("project_overrides", {}),
            )
        
        self._config_path = path
        self._loaded = True
    
    def get(self, name: str) -> IntentConfig | None:
        """按名称获取意图配置"""
        return self._intents.get(name)
    
    def list_intents(self) -> list[str]:
        """列出所有意图名称"""
        return list(self._intents.keys())
    
    def match_by_keywords(self, text: str, top_k: int = 3) -> list[IntentMatch]:
        """
        通过关键词匹配意图。
        
        参数:
            text: 用户输入文本
            top_k: 返回前 k 个匹配结果
        
        返回:
            匹配结果列表（按分数降序）
        """
        text_lower = text.lower()
        matches = []
        
        for intent in self._intents.values():
            matched_keywords = []
            for kw in intent.keywords:
                if kw.lower() in text_lower:
                    matched_keywords.append(kw)
            
            if matched_keywords:
                # 计算分数：匹配关键词数 / 总关键词数，加上优先级加成
                base_score = len(matched_keywords) / max(len(intent.keywords), 1)
                priority_bonus = intent.priority / 100.0
                score = min(base_score + priority_bonus, 1.0)
                
                matches.append(IntentMatch(
                    intent=intent,
                    score=score,
                    matched_keywords=matched_keywords,
                ))
        
        # 按分数降序排序
        matches.sort(key=lambda m: m.score, reverse=True)
        return matches[:top_k]
    
    def get_profile_for_intent(
        self,
        intent_name: str,
        project_id: str | None = None,
    ) -> str:
        """
        获取意图对应的 Profile 名称。
        
        优先级：
        1. project_overrides[project_id]
        2. intent.prompt_profile
        3. 默认映射（classifier_<intent_name>）
        """
        intent = self.get(intent_name)
        if not intent:
            return ""
        
        # 1. project 级覆盖
        if project_id and project_id in intent.project_overrides:
            return intent.project_overrides[project_id]
        
        # 2. 意图配置的 profile
        if intent.prompt_profile:
            return intent.prompt_profile
        
        # 3. 默认映射
        return f"classifier_{intent_name}"
    
    def get_profile_for_category(
        self,
        category: IntentCategory,
        project_id: str | None = None,
    ) -> str:
        """
        获取意图分类对应的 Profile 名称。
        
        用于 LLM 分类结果到 Profile 的映射。
        """
        return get_default_profile_for_category(category)
    
    @property
    def is_loaded(self) -> bool:
        """是否已加载配置"""
        return self._loaded
    
    def __len__(self) -> int:
        return len(self._intents)


# ============================================================
# 单例与便捷函数
# ============================================================

_default_intent_registry: IntentRegistry | None = None


def get_default_intent_registry(workspace_root: str | Path | None = None) -> IntentRegistry:
    """
    获取默认 Intent Registry（单例）。
    """
    global _default_intent_registry
    
    if _default_intent_registry is not None and _default_intent_registry.is_loaded:
        return _default_intent_registry
    
    _default_intent_registry = IntentRegistry()
    
    if workspace_root:
        root = Path(workspace_root)
        candidates = [
            root / ".clude" / "registry" / "intents.yaml",
            root / ".clude" / "registry" / "intents.example.yaml",
        ]
        for path in candidates:
            if path.exists():
                _default_intent_registry.load(path)
                break
    
    return _default_intent_registry


def reset_default_intent_registry() -> None:
    """重置默认 Registry（用于测试）"""
    global _default_intent_registry
    _default_intent_registry = None

