"""
ProjectPaths - 统一路径计算模块

功能：
- 根据 workspace_root 和 project_id 计算所有 .clude 相关路径
- 支持向后兼容（旧结构 .clude/logs/ 与新结构 .clude/projects/{project_id}/logs/）
- 支持自动创建目录

路径结构（新）：
    {workspace_root}/.clude/
    ├── projects/
    │   ├── default/           # project_id="default"
    │   │   ├── logs/
    │   │   │   ├── app.log
    │   │   │   ├── audit.jsonl
    │   │   │   └── trace.jsonl
    │   │   ├── sessions/
    │   │   ├── cache/
    │   │   │   └── markdown/
    │   │   └── vector_db/
    │   └── {custom_project}/
    └── registry/              # 全局注册表（跨项目共享）
        └── intents.yaml

向后兼容：
    - 如果检测到旧结构（.clude/logs/ 存在且不在 projects/ 下），
      可选择迁移或保持原样（通过 use_legacy_paths 参数控制）
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional


# 默认 project_id（未指定时使用）
DEFAULT_PROJECT_ID = "default"

# project_id 合法字符（字母、数字、下划线、连字符）
PROJECT_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")


class ProjectPaths:
    """
    统一路径计算器。
    
    使用示例：
        paths = ProjectPaths("/path/to/workspace", "myproj")
        paths.logs_dir()          # -> /path/to/workspace/.clude/projects/myproj/logs
        paths.audit_file()        # -> /path/to/workspace/.clude/projects/myproj/logs/audit.jsonl
        paths.sessions_dir()      # -> /path/to/workspace/.clude/projects/myproj/sessions
        paths.cache_dir("markdown") # -> /path/to/workspace/.clude/projects/myproj/cache/markdown
    """

    def __init__(
        self,
        workspace_root: str | Path,
        project_id: str | None = None,
        *,
        use_legacy_paths: bool = False,
        auto_create: bool = False,
    ) -> None:
        """
        初始化路径计算器。

        Args:
            workspace_root: 工作区根目录
            project_id: 项目 ID（默认 "default"）
            use_legacy_paths: 是否使用旧路径结构（.clude/logs/ 而非 .clude/projects/{pid}/logs/）
            auto_create: 是否自动创建目录
        """
        self._workspace_root = Path(workspace_root).resolve()
        self._project_id = self._validate_project_id(project_id)
        self._use_legacy = use_legacy_paths
        self._auto_create = auto_create

        # 基础目录
        self._clude_dir = self._workspace_root / ".clude"

    @staticmethod
    def _validate_project_id(project_id: str | None) -> str:
        """验证并规范化 project_id。"""
        if project_id is None:
            return DEFAULT_PROJECT_ID
        pid = str(project_id).strip()
        if not pid:
            return DEFAULT_PROJECT_ID
        if not PROJECT_ID_PATTERN.match(pid):
            raise ValueError(
                f"Invalid project_id '{pid}': 只能包含字母、数字、下划线和连字符"
            )
        return pid

    @property
    def workspace_root(self) -> Path:
        """工作区根目录。"""
        return self._workspace_root

    @property
    def project_id(self) -> str:
        """当前项目 ID。"""
        return self._project_id

    @property
    def clude_dir(self) -> Path:
        """
        .clude 根目录。
        
        返回: {workspace_root}/.clude
        """
        return self._clude_dir

    def project_dir(self) -> Path:
        """
        项目目录。
        
        新结构: {workspace_root}/.clude/projects/{project_id}
        旧结构: {workspace_root}/.clude
        """
        if self._use_legacy:
            return self._clude_dir
        return self._clude_dir / "projects" / self._project_id

    def _ensure_dir(self, path: Path) -> Path:
        """确保目录存在（如果 auto_create=True）。"""
        if self._auto_create:
            path.mkdir(parents=True, exist_ok=True)
        return path

    # ========== 日志相关 ==========

    def logs_dir(self) -> Path:
        """
        日志目录。
        
        新结构: .clude/projects/{project_id}/logs
        旧结构: .clude/logs
        """
        return self._ensure_dir(self.project_dir() / "logs")

    def app_log_file(self) -> Path:
        """应用日志文件: logs/app.log"""
        return self.logs_dir() / "app.log"

    def audit_file(self) -> Path:
        """审计日志文件: logs/audit.jsonl"""
        return self.logs_dir() / "audit.jsonl"

    def trace_file(self) -> Path:
        """追踪日志文件: logs/trace.jsonl"""
        return self.logs_dir() / "trace.jsonl"

    # ========== 会话相关 ==========

    def sessions_dir(self) -> Path:
        """
        会话存储目录。
        
        新结构: .clude/projects/{project_id}/sessions
        旧结构: .clude/sessions
        """
        return self._ensure_dir(self.project_dir() / "sessions")

    def session_file(self, session_id: str) -> Path:
        """特定会话文件: sessions/{session_id}.json"""
        return self.sessions_dir() / f"{session_id}.json"

    def latest_session_file(self) -> Path:
        """最新会话指针文件: sessions/latest.json"""
        return self.sessions_dir() / "latest.json"

    # ========== 缓存相关 ==========

    def cache_dir(self, subdir: str | None = None) -> Path:
        """
        缓存目录。
        
        新结构: .clude/projects/{project_id}/cache/{subdir}
        旧结构: .clude/{subdir}（如 .clude/markdown）
        
        Args:
            subdir: 子目录名（如 "markdown"）
        """
        if self._use_legacy:
            base = self._clude_dir / (subdir or "cache")
        else:
            base = self.project_dir() / "cache"
            if subdir:
                base = base / subdir
        return self._ensure_dir(base)

    def markdown_cache_dir(self) -> Path:
        """Markdown 缓存目录（webfetch 使用）。"""
        return self.cache_dir("markdown")

    # ========== 审批相关（Phase 2） ==========

    def approvals_dir(self) -> Path:
        """
        审批存储目录（按 project 隔离）。
        路径: .clude/projects/{project_id}/approvals
        """
        return self._ensure_dir(self.project_dir() / "approvals")

    def approval_file(self, approval_id: str) -> Path:
        """审批文件: approvals/{approval_id}.json"""
        return self.approvals_dir() / f"{approval_id}.json"

    # ========== 向量数据库 ==========

    def vector_db_dir(self) -> Path:
        """
        向量数据库目录。
        
        新结构: .clude/projects/{project_id}/vector_db
        旧结构: .clude/vector_db
        """
        return self._ensure_dir(self.project_dir() / "vector_db")

    # ========== 全局目录（跨项目共享） ==========

    def registry_dir(self) -> Path:
        """
        注册表目录（全局，跨项目共享）。
        
        路径: .clude/registry
        """
        return self._ensure_dir(self._clude_dir / "registry")

    def intents_file(self) -> Path:
        """意图注册表文件: registry/intents.yaml"""
        return self.registry_dir() / "intents.yaml"

    def prompt_versions_file(self, *, scope: str = "global") -> Path:
        """
        Prompt 版本指针文件（prompt_versions.json）。

        Args:
            scope:
              - "global": 全局共享（默认），路径：.clude/registry/prompt_versions.json
              - "project": 按 project 隔离，路径：.clude/projects/{project_id}/registry/prompt_versions.json
        """
        scope = (scope or "global").strip().lower()
        if scope not in {"global", "project"}:
            raise ValueError("scope must be 'global' or 'project'")
        if scope == "global":
            return self.registry_dir() / "prompt_versions.json"
        # project scope
        p = self.project_dir() / "registry"
        return self._ensure_dir(p) / "prompt_versions.json"

    # ========== 临时文件 ==========

    def temp_dir(self) -> Path:
        """
        临时文件目录。
        
        新结构: .clude/projects/{project_id}/temp
        旧结构: .clude/temp
        """
        return self._ensure_dir(self.project_dir() / "temp")

    # ========== 工具方法 ==========

    def has_legacy_structure(self) -> bool:
        """
        检测是否存在旧路径结构。
        
        判断依据：.clude/logs/ 存在 且 .clude/projects/ 不存在
        """
        old_logs = self._clude_dir / "logs"
        new_projects = self._clude_dir / "projects"
        return old_logs.exists() and not new_projects.exists()

    def migrate_to_project_structure(self, dry_run: bool = True) -> dict:
        """
        将旧结构迁移到新的项目结构。
        
        Args:
            dry_run: 如果为 True，只返回迁移计划，不实际执行
            
        Returns:
            迁移计划/结果字典
        """
        migrations = []
        
        # 需要迁移的目录映射
        old_to_new = [
            (self._clude_dir / "logs", self.logs_dir()),
            (self._clude_dir / "sessions", self.sessions_dir()),
            (self._clude_dir / "markdown", self.markdown_cache_dir()),
            (self._clude_dir / "vector_db", self.vector_db_dir()),
        ]
        
        for old_path, new_path in old_to_new:
            if old_path.exists() and not new_path.exists():
                migrations.append({
                    "from": str(old_path),
                    "to": str(new_path),
                    "exists": True,
                })
                if not dry_run:
                    new_path.parent.mkdir(parents=True, exist_ok=True)
                    old_path.rename(new_path)
        
        return {
            "dry_run": dry_run,
            "project_id": self._project_id,
            "migrations": migrations,
        }

    def __repr__(self) -> str:
        return (
            f"ProjectPaths(workspace_root={self._workspace_root!r}, "
            f"project_id={self._project_id!r}, "
            f"use_legacy={self._use_legacy})"
        )


# ========== 便捷函数 ==========

def get_project_paths(
    workspace_root: str | Path,
    project_id: str | None = None,
    *,
    auto_create: bool = False,
    auto_detect_legacy: bool = True,
) -> ProjectPaths:
    """
    获取 ProjectPaths 实例的便捷函数。
    
    Args:
        workspace_root: 工作区根目录
        project_id: 项目 ID（默认 "default"）
        auto_create: 是否自动创建目录
        auto_detect_legacy: 是否自动检测旧结构并使用
        
    Returns:
        ProjectPaths 实例
    """
    use_legacy = False
    if auto_detect_legacy:
        # 临时创建实例检测旧结构
        temp = ProjectPaths(workspace_root, project_id, use_legacy_paths=False)
        use_legacy = temp.has_legacy_structure()
    
    return ProjectPaths(
        workspace_root,
        project_id,
        use_legacy_paths=use_legacy,
        auto_create=auto_create,
    )


def resolve_path_template(
    path: str | None,
    *,
    workspace_root: str | Path,
    project_id: str | None = None,
) -> str | None:
    """
    解析路径模板，支持 {project_id} 占位符与默认路径映射。

    规则：
    1) 如果 path 为 None，直接返回 None
    2) 如果包含 {project_id}，直接替换
    3) 如果是默认 .clude 路径（如 .clude/logs/app.log），映射到 project 结构
    4) 其他情况保持不变（相对路径按 workspace_root 解析）
    """
    if path is None:
        return None
    raw = str(path).strip()
    if not raw:
        return None

    pid = project_id or DEFAULT_PROJECT_ID
    # 1) 显式模板替换
    if "{project_id}" in raw:
        raw = raw.replace("{project_id}", pid)

    paths = ProjectPaths(workspace_root, pid, auto_create=False)

    # 2) 默认 .clude 路径映射
    if raw in {".clude/logs/app.log", ".clude/logs/audit.jsonl", ".clude/logs/trace.jsonl"}:
        if raw.endswith("app.log"):
            return str(paths.app_log_file())
        if raw.endswith("audit.jsonl"):
            return str(paths.audit_file())
        return str(paths.trace_file())
    if raw in {".clude/markdown", ".clude/cache/markdown"}:
        return str(paths.markdown_cache_dir())
    if raw in {".clude/vector_db", ".clude/db", ".clude/vector-db"}:
        return str(paths.vector_db_dir())
    if raw in {".clude/sessions"}:
        return str(paths.sessions_dir())

    # 3) 其他相对路径：按 workspace_root 解析
    p = Path(raw)
    if p.is_absolute():
        return str(p)
    return str(Path(workspace_root) / p)

