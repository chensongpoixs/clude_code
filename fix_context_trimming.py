#!/usr/bin/env python3
"""
智能上下文裁剪策略修复方案
解决上下文裁剪过度导致重要信息丢失的问题
"""

import re
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum

class ContextPriority(Enum):
    """上下文优先级 - 重新定义"""
    CRITICAL = 5    # 系统提示词、核心指令、用户明确要求保留的信息
    HIGH = 4        # 当前任务相关信息、最近的重要对话、错误信息
    MEDIUM = 3      # 一般对话历史、工具执行结果摘要
    LOW = 2         # 重复性信息、冗余的日志输出
    TRIVIAL = 1     # 可以安全丢弃的信息

@dataclass
class SmartContextItem:
    """增强的上下文项，包含更多元信息"""
    content: str
    priority: ContextPriority
    category: str  # system, user, assistant, tool, error, etc.
    token_count: int = 0
    metadata: Dict[str, Any] = None
    created_at: float = 0
    importance_score: float = 0.0  # 新增：重要性评分
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
        if self.created_at == 0:
            import time
            self.created_at = time.time()

class SmartContextAnalyzer:
    """智能上下文分析器"""
    
    def __init__(self):
        # 重要关键词模式
        self.importance_patterns = {
            'error': [
                r'error', r'exception', r'failed', r'traceback',
                r'错误', r'异常', r'失败', r'报错'
            ],
            'user_request': [
                r'请', r'帮我', r'需要', r'希望',
                r'please', r'help', r'need', r'want'
            ],
            'code_content': [
                r'function', r'class', r'def ', r'import ',
                r'函数', r'类', r'定义', r'导入'
            ],
            'decision': [
                r'决定', r'选择', r'采用', r'使用',
                r'decide', r'choose', r'adopt', r'use'
            ]
        }
        
        # 保留模式
        self.preservation_patterns = [
            r'```[\s\S]*?```',  # 代码块
            r'".*?"',           # 引用的内容
            r'.*:\s*\d+',       # 行号引用
            r'File.*line.*',    # 文件路径引用
        ]
    
    def calculate_importance_score(self, item: SmartContextItem) -> float:
        """
        计算上下文项的重要性评分
        """
        score = 0.0
        content_lower = item.content.lower()
        
        # 1. 基础分类得分
        category_scores = {
            'system': 0.9,
            'user': 0.8,
            'assistant': 0.6,
            'tool': 0.5,
            'error': 1.0,  # 错误信息最重要
        }
        score += category_scores.get(item.category, 0.3)
        
        # 2. 关键词匹配得分
        for category, patterns in self.importance_patterns.items():
            for pattern in patterns:
                if re.search(pattern, content_lower, re.IGNORECASE):
                    weight = {'error': 0.3, 'user_request': 0.2, 'code_content': 0.15, 'decision': 0.1}
                    score += weight.get(category, 0.05)
        
        # 3. 内容特征得分
        if len(item.content) > 100:  # 较长内容可能包含更多信息
            score += 0.05
        
        if any(pattern in item.content for pattern in self.preservation_patterns):
            score += 0.15  # 包含重要格式的内容
        
        # 4. 时间衰减（新内容更重要）
        import time
        age = time.time() - item.created_at
        time_factor = max(0.1, 1.0 - age / 3600)  # 1小时内不衰减
        score *= time_factor
        
        return min(score, 1.0)
    
    def should_preserve_content(self, content: str) -> bool:
        """
        判断内容是否应该完整保留
        """
        preserve_reasons = []
        
        # 检查保留模式
        for pattern in self.preservation_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                preserve_reasons.append(f"匹配保留模式: {pattern[:20]}...")
        
        # 检查错误信息
        if any(re.search(p, content, re.IGNORECASE) for p in self.importance_patterns['error']):
            preserve_reasons.append("包含错误信息")
        
        # 检查代码块
        if content.count('```') >= 2:
            preserve_reasons.append("包含代码块")
        
        # 检查文件路径
        if re.search(r'[A-Za-z]:\[^\s]+|/[^\s]+', content):
            preserve_reasons.append("包含文件路径")
        
        return len(preserve_reasons) > 2  # 两个或以上理由才保留

class EnhancedContextManager:
    """增强的上下文管理器"""
    
    def __init__(self, max_tokens: int = 4000):
        self.max_tokens = max_tokens
        self.reserved_tokens = 1000
        self.available_tokens = max_tokens - self.reserved_tokens
        self.analyzer = SmartContextAnalyzer()
        self.context_items: List[SmartContextItem] = []
        
        # 裁剪策略配置
        self.preservation_threshold = 0.7  # 重要性阈值
        self.compression_ratio = 0.6      # 压缩比例
        
    def add_item(self, item: SmartContextItem):
        """添加上下文项并计算重要性"""
        item.importance_score = self.analyzer.calculate_importance_score(item)
        self.context_items.append(item)
    
    def smart_trim_context(self) -> List[SmartContextItem]:
        """
        智能裁剪上下文
        """
        if not self.context_items:
            return []
        
        # 1. 计算总token数
        total_tokens = sum(item.token_count for item in self.context_items)
        
        if total_tokens <= self.available_tokens:
            return self.context_items.copy()
        
        # 2. 按重要性排序
        sorted_items = sorted(self.context_items, key=lambda x: (
            -x.priority.value,           # 优先级高的在前
            -x.importance_score,        # 重要性高的在前
            -x.created_at              # 新的在前
        ))
        
        # 3. 分层选择
        result_items = []
        used_tokens = 0
        
        # 第一层：必须保留的内容
        for item in sorted_items:
            if item.priority == ContextPriority.CRITICAL:
                result_items.append(item)
                used_tokens += item.token_count
        
        # 第二层：重要性高的内容
        for item in sorted_items:
            if (item.priority in [ContextPriority.HIGH, ContextPriority.MEDIUM] and 
                item.importance_score >= self.preservation_threshold):
                if used_tokens + item.token_count <= self.available_tokens:
                    result_items.append(item)
                    used_tokens += item.token_count
        
        # 第三层：选择性保留和压缩
        remaining_items = [item for item in sorted_items if item not in result_items]
        
        for item in remaining_items:
            if used_tokens >= self.available_tokens:
                break
            
            # 检查是否应该完整保留
            if self.analyzer.should_preserve_content(item.content):
                if used_tokens + item.token_count <= self.available_tokens:
                    result_items.append(item)
                    used_tokens += item.token_count
            else:
                # 尝试压缩
                compressed_item = self.compress_item(item, self.available_tokens - used_tokens)
                if compressed_item:
                    result_items.append(compressed_item)
                    used_tokens += compressed_item.token_count
        
        return result_items
    
    def compress_item(self, item: SmartContextItem, max_allowed_tokens: int) -> Optional[SmartContextItem]:
        """
        智能压缩单个上下文项
        """
        if item.token_count <= max_allowed_tokens:
            return item
        
        # 根据内容类型选择压缩策略
        if item.category == 'tool':
            return self.compress_tool_result(item, max_allowed_tokens)
        elif item.category in ['user', 'assistant']:
            return self.compress_conversation(item, max_allowed_tokens)
        else:
            return self.generic_compress(item, max_allowed_tokens)
    
    def compress_tool_result(self, item: SmartContextItem, max_tokens: int) -> Optional[SmartContextItem]:
        """压缩工具执行结果"""
        content = item.content
        
        # 提取关键信息
        tool_name = item.metadata.get('tool_name', 'unknown')
        
        # 保留错误信息
        if any(keyword in content.lower() for keyword in ['error', 'failed', '错误', '失败']):
            summary = f"工具 {tool_name} 执行失败: {content[:200]}..."
        else:
            # 成功结果的摘要
            if len(content) > 100:
                summary = f"工具 {tool_name} 执行成功，结果长度: {len(content)} 字符"
            else:
                summary = f"工具 {tool_name} 执行结果: {content}"
        
        compressed = SmartContextItem(
            c
