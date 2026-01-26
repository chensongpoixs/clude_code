"""
Claude Code标准保护模块

提供智能保护机制，确保重要内容不会被错误压缩
"""

from .engine import (
    ProtectionEngine,
    get_protection_engine
)

__all__ = [
    'ProtectionEngine',
    'get_protection_engine'
]