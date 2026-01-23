"""
Prompt 加载器（增强版）

功能：
1. 读取 prompt 文件（支持 .md 和 .j2）
2. Jinja2 模板渲染（支持 if/for 等高级语法）
3. 版本化文件解析（xxx_v1.2.3.md）
4. YAML front matter 解析
5. 简单变量替换（兼容模式）
6. P3-1: LRU 缓存优化（基于文件 mtime）

对齐 agent_design_v_1.0.md 设计规范。
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


# ============================================================
# P3-1: 缓存系统
# ============================================================

@dataclass
class _CacheEntry:
    """缓存条目"""
    content: str
    metadata: "PromptMetadata"
    mtime: float  # 文件修改时间
    file_version: str


class _PromptCache:
    """
    P3-1: Prompt LRU 缓存
    
    特性：
    - 基于文件 mtime 的缓存有效性检查
    - 线程安全
    - 可配置的最大缓存数
    """
    
    def __init__(self, max_size: int = 100):
        self._cache: dict[str, _CacheEntry] = {}
        self._access_order: list[str] = []  # LRU 顺序
        self._max_size = max_size
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0
    
    def get(self, key: str, path: Path) -> _CacheEntry | None:
        """
        获取缓存（自动检查 mtime）。
        
        返回:
            缓存条目，None 如果未命中或已过期
        """
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._misses += 1
                return None
            
            # 检查文件是否已修改
            try:
                current_mtime = path.stat().st_mtime
                if current_mtime > entry.mtime:
                    # 文件已更新，缓存失效
                    del self._cache[key]
                    if key in self._access_order:
                        self._access_order.remove(key)
                    self._misses += 1
                    return None
            except OSError:
                # 文件不存在或无法访问
                self._misses += 1
                return None
            
            # 更新 LRU 顺序
            if key in self._access_order:
                self._access_order.remove(key)
            self._access_order.append(key)
            
            self._hits += 1
            return entry
    
    def put(self, key: str, entry: _CacheEntry) -> None:
        """添加缓存条目"""
        with self._lock:
            # LRU 淘汰
            while len(self._cache) >= self._max_size and self._access_order:
                oldest = self._access_order.pop(0)
                self._cache.pop(oldest, None)
            
            self._cache[key] = entry
            if key in self._access_order:
                self._access_order.remove(key)
            self._access_order.append(key)
    
    def clear(self) -> None:
        """清空缓存"""
        with self._lock:
            self._cache.clear()
            self._access_order.clear()
            self._hits = 0
            self._misses = 0
    
    @property
    def stats(self) -> dict[str, int]:
        """获取缓存统计"""
        with self._lock:
            total = self._hits + self._misses
            hit_rate = (self._hits / total * 100) if total > 0 else 0
            return {
                "hits": self._hits,
                "misses": self._misses,
                "size": len(self._cache),
                "max_size": self._max_size,
                "hit_rate": round(hit_rate, 1),
            }


# 全局缓存实例
_prompt_cache = _PromptCache(max_size=100)

# Jinja2 可选导入（优雅降级）
try:
    from jinja2 import Environment, BaseLoader, TemplateNotFound
    JINJA2_AVAILABLE = True
except ImportError:
    JINJA2_AVAILABLE = False
    Environment = None  # type: ignore
    BaseLoader = object  # type: ignore


# ============================================================
# 数据模型
# ============================================================

@dataclass
class PromptMetadata:
    """Prompt 元数据（来自 YAML front matter）"""
    title: str = ""
    version: str = ""
    layer: str = ""  # system | user
    tools_expected: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class PromptAsset:
    """Prompt 资产（完整信息）"""
    content: str
    metadata: PromptMetadata
    file_version: str  # 从文件名解析的版本（如 v1.2.3）
    path: str  # 相对路径


# ============================================================
# 路径与版本解析
# ============================================================

_PROMPTS_BASE = Path(__file__).resolve().parent

# 版本号正则：xxx_v1.2.3.md 或 xxx_v1.2.3.j2
_VERSION_PATTERN = re.compile(r"^(.+)_v(\d+\.\d+\.\d+)(\.(?:md|j2))$")


def _resolve_prompt_path(rel_path: str, version: str | None = None) -> Path:
    """
    解析 prompt 文件路径。
    
    参数:
        rel_path: 相对路径（如 "system/core/global.md"）
        version: 可选版本号（如 "1.2.3"），None 表示默认版本
    
    返回:
        完整文件路径
    """
    if version:
        # 构造版本化文件名：xxx.md -> xxx_v1.2.3.md
        p = Path(rel_path)
        versioned_name = f"{p.stem}_v{version}{p.suffix}"
        versioned_path = p.parent / versioned_name
        full_path = (_PROMPTS_BASE / versioned_path).resolve()
        if full_path.exists():
            return full_path
        # 版本化文件不存在，回退到默认
    
    return (_PROMPTS_BASE / rel_path).resolve()


def _parse_version_from_filename(filename: str) -> str:
    """从文件名解析版本号"""
    match = _VERSION_PATTERN.match(filename)
    if match:
        return match.group(2)
    return ""


def _security_check(path: Path) -> None:
    """安全检查：只允许读取 prompts 目录内部"""
    if _PROMPTS_BASE not in path.parents and path != _PROMPTS_BASE:
        raise ValueError(f"Prompt path escapes base directory: {path}")


# ============================================================
# YAML Front Matter 解析
# ============================================================

_FRONT_MATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _parse_front_matter(text: str) -> tuple[str, PromptMetadata]:
    """
    解析 YAML front matter。
    
    返回:
        (正文内容, 元数据)
    """
    match = _FRONT_MATTER_PATTERN.match(text)
    if not match:
        return text, PromptMetadata()
    
    yaml_str = match.group(1)
    content = text[match.end():]
    
    try:
        data = yaml.safe_load(yaml_str) or {}
        metadata = PromptMetadata(
            title=data.get("title", ""),
            version=data.get("version", ""),
            layer=data.get("layer", ""),
            tools_expected=data.get("tools_expected", []),
            constraints=data.get("constraints", []),
            raw=data,
        )
        return content, metadata
    except yaml.YAMLError:
        # YAML 解析失败，返回原文本
        return text, PromptMetadata()


# ============================================================
# Jinja2 渲染器
# ============================================================

class _PromptLoader(BaseLoader if JINJA2_AVAILABLE else object):
    """自定义 Jinja2 模板加载器"""
    
    def get_source(self, environment: Any, template: str) -> tuple[str, str, Any]:
        path = _resolve_prompt_path(template)
        _security_check(path)
        
        if not path.exists():
            if JINJA2_AVAILABLE:
                raise TemplateNotFound(template)
            raise FileNotFoundError(f"Template not found: {template}")
        
        source = path.read_text(encoding="utf-8", errors="replace")
        # 移除 front matter（Jinja2 不需要）
        content, _ = _parse_front_matter(source)
        
        return content, str(path), lambda: False


def _get_jinja_env() -> Any:
    """获取 Jinja2 环境（单例）"""
    if not JINJA2_AVAILABLE:
        return None
    
    if not hasattr(_get_jinja_env, "_env"):
        _get_jinja_env._env = Environment(  # type: ignore
            loader=_PromptLoader(),
            autoescape=False,
            keep_trailing_newline=True,
        )
    return _get_jinja_env._env  # type: ignore


# ============================================================
# 简单变量替换（兼容模式）
# ============================================================

_VAR_RE = re.compile(r"\{\{\s*([a-zA-Z_]\w*)\s*\}\}")


def _simple_render(text: str, **variables: object) -> str:
    """简单变量替换（不支持 if/for）"""
    def _repl(m: re.Match[str]) -> str:
        key = m.group(1)
        val = variables.get(key, "")
        return "" if val is None else str(val)
    return _VAR_RE.sub(_repl, text)


# ============================================================
# 公开接口
# ============================================================

def read_prompt(rel_path: str, version: str | None = None) -> str:
    """
    读取 prompt 文件内容（带缓存）。
    
    参数:
        rel_path: 相对于 prompts/ 的路径（如 "system/core/global.md"）
        version: 可选版本号（如 "1.2.3"），None = 默认版本
    
    返回:
        文件内容（不含 YAML front matter）
    """
    path = _resolve_prompt_path(rel_path, version)
    _security_check(path)
    
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {rel_path}")
    
    # P3-1: 尝试从缓存获取
    cache_key = f"{rel_path}@{version or 'default'}"
    cached = _prompt_cache.get(cache_key, path)
    if cached:
        return cached.content
    
    # 缓存未命中，读取文件
    text = path.read_text(encoding="utf-8", errors="replace")
    content, metadata = _parse_front_matter(text)
    file_version = _parse_version_from_filename(path.name)
    
    # 存入缓存
    _prompt_cache.put(cache_key, _CacheEntry(
        content=content,
        metadata=metadata,
        mtime=path.stat().st_mtime,
        file_version=file_version,
    ))
    
    return content


def render_prompt(rel_path: str, version: str | None = None, **variables: object) -> str:
    """
    渲染 prompt 模板。
    
    - 对于 .j2 文件：使用 Jinja2 渲染（支持 if/for/include 等）
    - 对于 .md 文件：使用简单变量替换
    - 如果 Jinja2 不可用：统一使用简单变量替换
    
    参数:
        rel_path: 相对路径
        version: 可选版本号
        **variables: 模板变量
    
    返回:
        渲染后的内容
    """
    path = _resolve_prompt_path(rel_path, version)
    _security_check(path)
    
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {rel_path}")
    
    text = path.read_text(encoding="utf-8", errors="replace")
    content, _ = _parse_front_matter(text)
    
    # 判断是否使用 Jinja2
    use_jinja = rel_path.endswith(".j2") and JINJA2_AVAILABLE
    
    if use_jinja:
        env = _get_jinja_env()
        template = env.from_string(content)
        return template.render(**variables)
    else:
        return _simple_render(content, **variables)


def load_prompt_asset(rel_path: str, version: str | None = None) -> PromptAsset:
    """
    加载完整的 prompt 资产（含元数据，带缓存）。
    
    参数:
        rel_path: 相对路径
        version: 可选版本号
    
    返回:
        PromptAsset 对象
    """
    path = _resolve_prompt_path(rel_path, version)
    _security_check(path)
    
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {rel_path}")
    
    # P3-1: 尝试从缓存获取
    cache_key = f"{rel_path}@{version or 'default'}"
    cached = _prompt_cache.get(cache_key, path)
    if cached:
        return PromptAsset(
            content=cached.content,
            metadata=cached.metadata,
            file_version=cached.file_version or cached.metadata.version,
            path=rel_path,
        )
    
    # 缓存未命中，读取文件
    text = path.read_text(encoding="utf-8", errors="replace")
    content, metadata = _parse_front_matter(text)
    file_version = _parse_version_from_filename(path.name)
    
    # 存入缓存
    _prompt_cache.put(cache_key, _CacheEntry(
        content=content,
        metadata=metadata,
        mtime=path.stat().st_mtime,
        file_version=file_version,
    ))
    
    return PromptAsset(
        content=content,
        metadata=metadata,
        file_version=file_version or metadata.version,
        path=rel_path,
    )


def list_prompt_versions(rel_path: str) -> list[str]:
    """
    列出指定 prompt 的所有可用版本。
    
    参数:
        rel_path: 相对路径（如 "system/core/global.md"）
    
    返回:
        版本号列表（如 ["1.0.0", "1.1.0"]），空列表表示只有默认版本
    """
    p = Path(rel_path)
    parent = _PROMPTS_BASE / p.parent
    stem = p.stem
    suffix = p.suffix
    
    if not parent.exists():
        return []
    
    versions = []
    pattern = re.compile(rf"^{re.escape(stem)}_v(\d+\.\d+\.\d+){re.escape(suffix)}$")
    
    for f in parent.iterdir():
        if f.is_file():
            match = pattern.match(f.name)
            if match:
                versions.append(match.group(1))
    
    return sorted(versions)


# ============================================================
# 便捷函数
# ============================================================

def render_system_prompt(
    core_path: str = "system/core/global.md",
    role_path: str | None = None,
    policy_path: str | None = None,
    context_path: str | None = None,
    **context_vars: object,
) -> str:
    """
    组合渲染 System Prompt（四层模型）。
    
    参数:
        core_path: Core 层路径（必选）
        role_path: Role 层路径（可选）
        policy_path: Policy 层路径（可选）
        context_path: Context 层路径（可选）
        **context_vars: Context 模板变量
    
    返回:
        组合后的 System Prompt
    """
    parts = []
    
    # Core（必选）
    parts.append(read_prompt(core_path))
    
    # Role（可选）
    if role_path:
        parts.append(read_prompt(role_path))
    
    # Policy（可选）
    if policy_path:
        parts.append(read_prompt(policy_path))
    
    # Context（可选，支持变量）
    if context_path:
        parts.append(render_prompt(context_path, **context_vars))
    
    return "\n\n".join(parts)


# ============================================================
# P3-1: 缓存控制接口
# ============================================================

def get_cache_stats() -> dict[str, int]:
    """获取缓存统计信息"""
    return _prompt_cache.stats


def clear_cache() -> None:
    """清空 prompt 缓存"""
    _prompt_cache.clear()


def set_cache_max_size(max_size: int) -> None:
    """设置缓存最大容量"""
    global _prompt_cache
    old_cache = _prompt_cache
    _prompt_cache = _PromptCache(max_size=max_size)
    # 可选：复制旧缓存数据（暂不实现，直接清空更简单）
