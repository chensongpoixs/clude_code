"""
企业策略下发系统

业界对比：
- GitHub Copilot Enterprise: 组织级策略管理
- Cursor Enterprise: 远程配置 + 审计
- Claude for Enterprise: RBAC + 合规审计

本实现：远程策略拉取 + 本地缓存 + RBAC 模型 + 审计集成
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Literal, Set
from enum import Enum

from pydantic import BaseModel, Field, ValidationError


class Permission(str, Enum):
    """权限枚举。"""
    # 文件操作
    FILE_READ = "file:read"
    FILE_WRITE = "file:write"
    FILE_DELETE = "file:delete"
    
    # 命令执行
    CMD_EXEC = "cmd:exec"
    CMD_NETWORK = "cmd:network"
    CMD_SUDO = "cmd:sudo"
    
    # 工具使用
    TOOL_LSP = "tool:lsp"
    TOOL_PLUGIN = "tool:plugin"
    TOOL_SEMANTIC = "tool:semantic"
    
    # 系统操作
    SYS_CONFIG = "sys:config"
    SYS_AUDIT_VIEW = "sys:audit_view"
    SYS_POLICY_EDIT = "sys:policy_edit"


class Role(BaseModel):
    """角色定义。"""
    name: str = Field(..., description="角色名")
    description: str = Field("", description="角色描述")
    permissions: Set[Permission] = Field(default_factory=set, description="权限集合")
    
    def has_permission(self, permission: Permission) -> bool:
        return permission in self.permissions


# 预定义角色
PREDEFINED_ROLES = {
    "admin": Role(
        name="admin",
        description="管理员，拥有所有权限",
        permissions=set(Permission),
    ),
    "developer": Role(
        name="developer",
        description="开发者，可执行代码相关操作",
        permissions={
            Permission.FILE_READ,
            Permission.FILE_WRITE,
            Permission.CMD_EXEC,
            Permission.TOOL_LSP,
            Permission.TOOL_PLUGIN,
            Permission.TOOL_SEMANTIC,
        },
    ),
    "reviewer": Role(
        name="reviewer",
        description="代码审查者，只读权限",
        permissions={
            Permission.FILE_READ,
            Permission.TOOL_LSP,
            Permission.TOOL_SEMANTIC,
            Permission.SYS_AUDIT_VIEW,
        },
    ),
    "guest": Role(
        name="guest",
        description="访客，最小权限",
        permissions={
            Permission.FILE_READ,
        },
    ),
}


class User(BaseModel):
    """用户定义。"""
    id: str = Field(..., description="用户 ID")
    name: str = Field(..., description="用户名")
    email: Optional[str] = Field(None, description="邮箱")
    roles: List[str] = Field(default_factory=list, description="角色列表")
    extra_permissions: Set[Permission] = Field(default_factory=set, description="额外权限")
    denied_permissions: Set[Permission] = Field(default_factory=set, description="禁止权限")
    
    def get_effective_permissions(self, role_registry: Dict[str, Role]) -> Set[Permission]:
        """计算有效权限（角色权限 + 额外权限 - 禁止权限）。"""
        perms: Set[Permission] = set()
        
        # 角色权限
        for role_name in self.roles:
            role = role_registry.get(role_name) or PREDEFINED_ROLES.get(role_name)
            if role:
                perms |= role.permissions
        
        # 额外权限
        perms |= self.extra_permissions
        
        # 禁止权限
        perms -= self.denied_permissions
        
        return perms


class PathRule(BaseModel):
    """路径规则（用于文件访问控制）。"""
    pattern: str = Field(..., description="路径模式（支持 glob）")
    allow: bool = Field(True, description="是否允许")
    permissions: Set[Permission] = Field(default_factory=set, description="适用的权限")


class CommandRule(BaseModel):
    """命令规则（用于命令执行控制）。"""
    pattern: str = Field(..., description="命令模式（正则表达式）")
    allow: bool = Field(True, description="是否允许")
    reason: str = Field("", description="规则原因/说明")


class EnterprisePolicy(BaseModel):
    """
    企业策略定义。
    
    可通过远程服务器下发或本地配置。
    """
    # 元数据
    version: str = Field("1.0.0", description="策略版本")
    organization: str = Field("", description="组织名称")
    effective_from: Optional[datetime] = Field(None, description="生效时间")
    effective_until: Optional[datetime] = Field(None, description="失效时间")
    
    # 用户与角色
    roles: Dict[str, Role] = Field(default_factory=dict, description="自定义角色")
    users: Dict[str, User] = Field(default_factory=dict, description="用户列表")
    default_role: str = Field("guest", description="默认角色")
    
    # 路径规则
    path_rules: List[PathRule] = Field(default_factory=list, description="路径访问规则")
    
    # 命令规则
    command_rules: List[CommandRule] = Field(default_factory=list, description="命令执行规则")
    command_denylist: List[str] = Field(default_factory=list, description="命令黑名单")
    command_allowlist: List[str] = Field(default_factory=list, description="命令白名单")
    
    # 全局开关
    allow_network: bool = Field(False, description="是否允许网络访问")
    allow_sudo: bool = Field(False, description="是否允许 sudo")
    require_confirmation: bool = Field(True, description="是否需要写操作确认")
    
    # 审计配置
    audit_enabled: bool = Field(True, description="是否启用审计")
    audit_retention_days: int = Field(90, description="审计日志保留天数")
    
    # 插件配置
    allowed_plugins: List[str] = Field(default_factory=list, description="允许的插件列表（空=全部允许）")
    blocked_plugins: List[str] = Field(default_factory=list, description="禁止的插件列表")
    
    def is_effective(self) -> bool:
        """检查策略是否在有效期内。"""
        now = datetime.now()
        if self.effective_from and now < self.effective_from:
            return False
        if self.effective_until and now > self.effective_until:
            return False
        return True


@dataclass
class PolicyDecision:
    """策略决策结果。"""
    allowed: bool
    reason: str = ""
    required_permissions: Set[Permission] = field(default_factory=set)
    missing_permissions: Set[Permission] = field(default_factory=set)


class PolicyEngine:
    """
    策略引擎。
    
    功能：
    - 远程策略拉取与缓存
    - RBAC 权限校验
    - 路径/命令规则匹配
    - 决策审计
    """
    
    def __init__(
        self,
        workspace_root: Path,
        policy_server_url: str | None = None,
        cache_ttl_s: int = 3600,
    ):
        self.workspace_root = workspace_root.resolve()
        self.policy_server_url = policy_server_url
        self.cache_ttl_s = cache_ttl_s
        
        self._policy: EnterprisePolicy | None = None
        self._cache_path = self.workspace_root / ".clude" / "policy_cache.json"
        self._cache_time: float = 0
        self._current_user: User | None = None
        
        self._load_policy()
    
    def _load_policy(self) -> None:
        """加载策略（优先远程，降级缓存，最后默认）。"""
        # 1. 尝试从远程拉取
        if self.policy_server_url:
            remote_policy = self._fetch_remote_policy()
            if remote_policy:
                self._policy = remote_policy
                self._save_cache()
                return
        
        # 2. 尝试从缓存加载
        cached_policy = self._load_cache()
        if cached_policy:
            self._policy = cached_policy
            return
        
        # 3. 使用本地配置文件
        local_policy = self._load_local_config()
        if local_policy:
            self._policy = local_policy
            return
        
        # 4. 使用默认策略
        self._policy = EnterprisePolicy()
    
    def _fetch_remote_policy(self) -> EnterprisePolicy | None:
        """从远程服务器拉取策略。"""
        if not self.policy_server_url:
            return None
        
        try:
            import httpx
            
            with httpx.Client(timeout=30) as client:
                response = client.get(
                    self.policy_server_url,
                    headers={"Accept": "application/json"},
                )
                
                if response.is_success:
                    data = response.json()
                    return EnterprisePolicy.model_validate(data)
                    
        except Exception:
            pass
        
        return None
    
    def _load_cache(self) -> EnterprisePolicy | None:
        """从缓存加载策略。"""
        if not self._cache_path.exists():
            return None
        
        try:
            cache_data = json.loads(self._cache_path.read_text(encoding="utf-8"))
            
            # 检查缓存是否过期
            cache_time = cache_data.get("_cache_time", 0)
            if time.time() - cache_time > self.cache_ttl_s:
                return None
            
            self._cache_time = cache_time
            return EnterprisePolicy.model_validate(cache_data.get("policy", {}))
            
        except Exception:
            return None
    
    def _save_cache(self) -> None:
        """保存策略到缓存。"""
        if not self._policy:
            return
        
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_data = {
                "_cache_time": time.time(),
                "policy": self._policy.model_dump(mode="json"),
            }
            self._cache_path.write_text(
                json.dumps(cache_data, indent=2, ensure_ascii=False, default=str),
                encoding="utf-8",
            )
            self._cache_time = time.time()
        except Exception:
            pass
    
    def _load_local_config(self) -> EnterprisePolicy | None:
        """从本地配置文件加载策略。"""
        config_paths = [
            self.workspace_root / ".clude" / "policy.json",
            self.workspace_root / ".clude" / "policy.yaml",
            self.workspace_root / "clude-policy.json",
            self.workspace_root / "clude-policy.yaml",
        ]
        
        for path in config_paths:
            if path.exists():
                try:
                    content = path.read_text(encoding="utf-8")
                    
                    if path.suffix in (".yaml", ".yml"):
                        import yaml
                        data = yaml.safe_load(content)
                    else:
                        data = json.loads(content)
                    
                    return EnterprisePolicy.model_validate(data)
                    
                except Exception:
                    continue
        
        return None
    
    def set_current_user(self, user_id: str) -> bool:
        """设置当前用户（用于 RBAC 校验）。"""
        if not self._policy:
            return False
        
        if user_id in self._policy.users:
            self._current_user = self._policy.users[user_id]
            return True
        
        # 创建默认用户
        self._current_user = User(
            id=user_id,
            name=user_id,
            roles=[self._policy.default_role],
        )
        return True
    
    def get_current_permissions(self) -> Set[Permission]:
        """获取当前用户的有效权限。"""
        if not self._current_user or not self._policy:
            return set()
        
        role_registry = {**PREDEFINED_ROLES, **self._policy.roles}
        return self._current_user.get_effective_permissions(role_registry)
    
    def check_permission(self, permission: Permission) -> PolicyDecision:
        """检查当前用户是否有指定权限。"""
        current_perms = self.get_current_permissions()
        
        if permission in current_perms:
            return PolicyDecision(allowed=True)
        
        return PolicyDecision(
            allowed=False,
            reason=f"缺少权限: {permission.value}",
            required_permissions={permission},
            missing_permissions={permission},
        )
    
    def check_file_access(self, path: str, operation: Literal["read", "write", "delete"]) -> PolicyDecision:
        """检查文件访问权限。"""
        if not self._policy:
            return PolicyDecision(allowed=True)
        
        # 映射操作到权限
        perm_map = {
            "read": Permission.FILE_READ,
            "write": Permission.FILE_WRITE,
            "delete": Permission.FILE_DELETE,
        }
        required_perm = perm_map.get(operation, Permission.FILE_READ)
        
        # 检查基本权限
        perm_decision = self.check_permission(required_perm)
        if not perm_decision.allowed:
            return perm_decision
        
        # 检查路径规则
        import fnmatch
        for rule in self._policy.path_rules:
            if fnmatch.fnmatch(path, rule.pattern):
                if not rule.allow:
                    return PolicyDecision(
                        allowed=False,
                        reason=f"路径被策略禁止: {rule.pattern}",
                    )
                # 如果匹配到允许规则，继续检查其他规则
        
        return PolicyDecision(allowed=True)
    
    def check_command(self, command: str) -> PolicyDecision:
        """检查命令执行权限。"""
        if not self._policy:
            return PolicyDecision(allowed=True)
        
        # 检查基本权限
        perm_decision = self.check_permission(Permission.CMD_EXEC)
        if not perm_decision.allowed:
            return perm_decision
        
        # 检查黑名单
        import re
        for pattern in self._policy.command_denylist:
            if re.search(pattern, command, re.IGNORECASE):
                return PolicyDecision(
                    allowed=False,
                    reason=f"命令被策略禁止: 匹配黑名单模式 {pattern}",
                )
        
        # 检查白名单（如果有白名单，命令必须匹配）
        if self._policy.command_allowlist:
            matched = False
            for pattern in self._policy.command_allowlist:
                if re.search(pattern, command, re.IGNORECASE):
                    matched = True
                    break
            if not matched:
                return PolicyDecision(
                    allowed=False,
                    reason="命令未在白名单中",
                )
        
        # 检查命令规则
        for rule in self._policy.command_rules:
            if re.search(rule.pattern, command, re.IGNORECASE):
                if not rule.allow:
                    return PolicyDecision(
                        allowed=False,
                        reason=rule.reason or f"命令被策略禁止: {rule.pattern}",
                    )
        
        # 检查网络访问
        network_commands = ["curl", "wget", "ssh", "scp", "rsync", "ftp", "telnet"]
        if any(cmd in command.lower() for cmd in network_commands):
            if not self._policy.allow_network:
                net_decision = self.check_permission(Permission.CMD_NETWORK)
                if not net_decision.allowed:
                    return PolicyDecision(
                        allowed=False,
                        reason="网络访问被策略禁止",
                    )
        
        # 检查 sudo
        if "sudo" in command.lower():
            if not self._policy.allow_sudo:
                sudo_decision = self.check_permission(Permission.CMD_SUDO)
                if not sudo_decision.allowed:
                    return PolicyDecision(
                        allowed=False,
                        reason="sudo 被策略禁止",
                    )
        
        return PolicyDecision(allowed=True)
    
    def check_plugin(self, plugin_name: str) -> PolicyDecision:
        """检查插件使用权限。"""
        if not self._policy:
            return PolicyDecision(allowed=True)
        
        # 检查基本权限
        perm_decision = self.check_permission(Permission.TOOL_PLUGIN)
        if not perm_decision.allowed:
            return perm_decision
        
        # 检查黑名单
        if plugin_name in self._policy.blocked_plugins:
            return PolicyDecision(
                allowed=False,
                reason=f"插件被策略禁止: {plugin_name}",
            )
        
        # 检查白名单
        if self._policy.allowed_plugins and plugin_name not in self._policy.allowed_plugins:
            return PolicyDecision(
                allowed=False,
                reason=f"插件未在允许列表中: {plugin_name}",
            )
        
        return PolicyDecision(allowed=True)
    
    def requires_confirmation(self) -> bool:
        """检查是否需要写操作确认。"""
        if not self._policy:
            return True
        return self._policy.require_confirmation
    
    def get_policy_summary(self) -> Dict[str, Any]:
        """获取策略摘要（用于 UI 展示）。"""
        if not self._policy:
            return {"status": "no_policy"}
        
        return {
            "version": self._policy.version,
            "organization": self._policy.organization,
            "effective": self._policy.is_effective(),
            "allow_network": self._policy.allow_network,
            "allow_sudo": self._policy.allow_sudo,
            "require_confirmation": self._policy.require_confirmation,
            "audit_enabled": self._policy.audit_enabled,
            "roles_count": len(self._policy.roles),
            "users_count": len(self._policy.users),
            "current_user": self._current_user.id if self._current_user else None,
            "current_permissions": [p.value for p in self.get_current_permissions()],
        }
    
    def export_policy(self, format: Literal["json", "yaml"] = "json") -> str:
        """导出当前策略。"""
        if not self._policy:
            return "{}" if format == "json" else ""
        
        data = self._policy.model_dump(mode="json", exclude_none=True)
        
        if format == "yaml":
            import yaml
            return yaml.dump(data, default_flow_style=False, allow_unicode=True)
        
        return json.dumps(data, indent=2, ensure_ascii=False, default=str)

