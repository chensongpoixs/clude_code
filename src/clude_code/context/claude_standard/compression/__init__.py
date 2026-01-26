"""
Claude Code标准压缩模块

提供智能压缩算法，实现多层级的token优化策略
"""

from .engine import (
    CompressionEngine,
    get_compression_engine
)

__all__ = [
    'CompressionEngine',
    'get_compression_engine'
]