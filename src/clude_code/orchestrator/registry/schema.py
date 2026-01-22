"""
Intent Registry Schema - 意图注册表数据模型

定义 YAML 配置的 Pydantic Schema：
- IntentSpec: 单个意图配置
- ProjectConfig: 项目级配置（包含多个意图）

YAML 配置示例（.clude/registry/intents.yaml）：
```yaml
version: "1.0"
default_risk_level: MEDIUM
intents:
  - name: code_review
    keywords: ["review", "审查", "code review"]
    mode: unified
    risk_level: LOW
    prompt_ref: agent_loop/code_review_prompt.j2
    prompt_version: "1.0"
    tools:
      - read_file
      - grep
      - list_dir
    description: "代码审查任务"
    
  - name: file_modification
    keywords: ["修改", "write", "创建文件"]
    mode: unified
    risk_level: MEDIUM
    prompt_ref: agent_loop/file_mod_prompt.j2
    tools:
      - read_file
      - write_file
      - apply_patch
    description: "文件修改任务"
```
"""

from __future__ import annotations

from enum import Enum
from typing import Optional, Any
from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    """风险等级"""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class IntentSpec(BaseModel):
    """
    意图规范（Intent Specification）
    
    定义单个意图的配置：触发关键词、风险等级、Prompt 引用、允许的工具集合等。
    """
    name: str = Field(..., description="意图名称（唯一标识）")
    keywords: list[str] = Field(default_factory=list, description="触发关键词列表（用于匹配用户输入）")
    mode: str = Field(default="unified", description="执行模式：unified（统一规划）或 split（分步）")
    risk_level: RiskLevel = Field(default=RiskLevel.MEDIUM, description="风险等级")
    # ===== 旧字段（兼容映射）=====
    # 历史上仅支持单一 prompt_ref/prompt_version；新体系改为按 stage 的三层 prompts。
    prompt_ref: Optional[str] = Field(default=None, description="(deprecated) 旧 prompt 引用，将映射到 prompts.planning.task.ref")
    prompt_version: Optional[str] = Field(default=None, description="(deprecated) 旧 prompt 版本，将映射到 prompts.planning.task.version")

    # ===== 新字段：按阶段(stage)的三层 Prompt 配置 =====
    prompts: Optional["StagePrompts"] = Field(default=None, description="按阶段的三层 prompt 配置（intent 级覆盖）")
    prompt_profile: Optional[str] = Field(default=None, description="Prompt Profile 名称（推荐）：Intent 通过 profile 间接选择 system/user prompts")
    tools: list[str] = Field(default_factory=list, description="允许使用的工具列表（空表示不限制）")
    description: Optional[str] = Field(default=None, description="意图描述")
    enabled: bool = Field(default=True, description="是否启用")
    priority: int = Field(default=0, description="优先级（数值越大越优先）")

    class Config:
        use_enum_values = True


class ProjectConfig(BaseModel):
    """
    项目级配置（Project Configuration）
    
    包含一个项目下的所有意图配置。
    """
    version: str = Field(default="1.0", description="配置版本")
    project_id: Optional[str] = Field(default=None, description="项目 ID（可选，用于覆盖全局默认）")
    default_risk_level: RiskLevel = Field(default=RiskLevel.MEDIUM, description="默认风险等级")
    default_mode: str = Field(default="unified", description="默认执行模式")
    intents: list[IntentSpec] = Field(default_factory=list, description="意图列表")
    
    # 项目级工具限制（空表示不限制）
    allowed_tools: list[str] = Field(default_factory=list, description="项目允许的工具列表（为空则不限制）")
    blocked_tools: list[str] = Field(default_factory=list, description="项目禁用的工具列表")
    
    # ===== 新字段：项目级默认 stage prompts =====
    prompts: Optional["StagePrompts"] = Field(default=None, description="按阶段的三层 prompt 配置（project 级默认）")

    # ===== 旧字段（兼容保留，后续可移除）=====
    base_prompt_ref: Optional[str] = Field(default=None, description="(deprecated) 项目级 Base Prompt 引用")
    domain_prompt_ref: Optional[str] = Field(default=None, description="(deprecated) 项目级 Domain Prompt 引用")
    base_prompt_version: Optional[str] = Field(default=None, description="(deprecated) 项目级 Base Prompt 版本（精确 SemVer）")
    domain_prompt_version: Optional[str] = Field(default=None, description="(deprecated) 项目级 Domain Prompt 版本（精确 SemVer）")
    
    class Config:
        use_enum_values = True

    def get_intent_by_name(self, name: str) -> Optional[IntentSpec]:
        """根据名称获取意图配置。"""
        for intent in self.intents:
            if intent.name == name and intent.enabled:
                return intent
        return None

    def normalize(self) -> "ProjectConfig":
        """
        规范化配置：把旧字段映射到新 prompts 结构，避免历史配置直接失效。
        """
        # project 级旧字段 -> prompts.planning.base/domain（仅作为兜底）
        if self.prompts is None:
            self.prompts = StagePrompts()
        # 旧 project 字段仅用于 planning 阶段（与 AgentLoop 旧实现对齐）
        if (self.base_prompt_ref or self.domain_prompt_ref) and getattr(self.prompts, "planning", None) is None:
            self.prompts.planning = PromptStage()
        if self.base_prompt_ref and self.prompts and self.prompts.planning and self.prompts.planning.base is None:
            self.prompts.planning.base = PromptLayer(ref=self.base_prompt_ref, version=self.base_prompt_version)
        if self.domain_prompt_ref and self.prompts and self.prompts.planning and self.prompts.planning.domain is None:
            self.prompts.planning.domain = PromptLayer(ref=self.domain_prompt_ref, version=self.domain_prompt_version)

        # intent 级旧字段 -> prompts.planning.task
        for it in self.intents:
            if it.prompts is None:
                it.prompts = StagePrompts()
            if (it.prompt_ref or it.prompt_version) and getattr(it.prompts, "planning", None) is None:
                it.prompts.planning = PromptStage()
            if it.prompt_ref and it.prompts and it.prompts.planning and it.prompts.planning.task is None:
                it.prompts.planning.task = PromptLayer(ref=it.prompt_ref, version=it.prompt_version)
        return self


class PromptLayer(BaseModel):
    """三层中的单层引用（ref + 可选 version）。"""
    ref: str = Field(..., description="prompt 文件引用（相对 prompts/）")
    version: Optional[str] = Field(default=None, description="精确 SemVer；为空则走 prompt_versions.json current 指针")


class PromptStage(BaseModel):
    """一个 stage 的三层组合：base/domain/task。"""
    base: Optional[PromptLayer] = Field(default=None)
    domain: Optional[PromptLayer] = Field(default=None)
    task: Optional[PromptLayer] = Field(default=None)


class StagePrompts(BaseModel):
    """
    按阶段(stage)的 prompt 配置。
    说明：每个 stage 都可以配置三层（base/domain/task），并支持 version。
    """
    system: Optional[PromptStage] = Field(default=None, description="system prompt")
    user_prompt: Optional[PromptStage] = Field(default=None, description="user prompt template（用于结构化用户输入，禁止直接用 raw user_text）")
    planning: Optional[PromptStage] = Field(default=None, description="planning prompt")
    execute_step: Optional[PromptStage] = Field(default=None, description="execute step prompt")
    replan: Optional[PromptStage] = Field(default=None, description="replan prompt")
    plan_patch_retry: Optional[PromptStage] = Field(default=None, description="plan patch retry prompt")
    plan_parse_retry: Optional[PromptStage] = Field(default=None, description="plan parse retry prompt")
    invalid_step_output_retry: Optional[PromptStage] = Field(default=None, description="invalid step output retry prompt")
    intent_classify: Optional[PromptStage] = Field(default=None, description="intent classify prompt")


class PromptProfileSpec(BaseModel):
    """
    Prompt Profile 规范（MVP）：
    - 复用 StagePrompts（支持 system/user_prompt 两个关键 stage）
    - 可扩展：未来可在 profile 中承载风险/工具集合等统一约束
    """
    name: str = Field(..., description="profile 名称（唯一）")
    description: Optional[str] = Field(default=None, description="profile 描述")
    risk_level: RiskLevel = Field(default=RiskLevel.MEDIUM, description="profile 级风险等级（可用于与 intent 合并）")
    prompts: StagePrompts = Field(default_factory=StagePrompts, description="profile 提示词配置（按 stage）")


class PromptProfilesConfig(BaseModel):
    version: str = Field(default="1.0")
    prompt_profiles: dict[str, PromptProfileSpec] = Field(default_factory=dict, description="profile 映射表：name -> spec")


