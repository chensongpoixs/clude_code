#!/usr/bin/env python3
"""
任务复杂度判断改进方案
解决复杂多步骤任务的意图识别不准确问题
"""

import re
from typing import Dict, List, Tuple
from dataclasses import dataclass
from enum import Enum

class TaskComplexityLevel(Enum):
    SIMPLE = 1      # 简单任务：单一操作，明确结果
    MODERATE = 2    # 中等任务：2-3个步骤，需要基本规划
    COMPLEX = 3     # 复杂任务：多步骤，需要详细规划
    ADVANCED = 4    # 高级任务：涉及多个技术栈，需要架构设计

@dataclass
class TaskComplexityResult:
    """任务复杂度分析结果"""
    level: TaskComplexityLevel
    confidence: float
    factors: List[str]  # 影响复杂度的因素
    estimated_steps: int
    suggested_approach: str

class TaskComplexityAnalyzer:
    """任务复杂度分析器"""
    
    def __init__(self):
        # 复杂度指标权重
        self.weights = {
            'keyword_count': 0.2,
            'step_indicators': 0.25,
            'technical_stack': 0.2,
            'text_length': 0.1,
            'uncertainty': 0.15,
            'dependencies': 0.1
        }
        
        # 简单任务关键词
        self.simple_keywords = {
            '显示', '列出', '查看', '检查', '获取', '读取', '搜索', '查找',
            'show', 'list', 'display', 'check', 'get', 'read', 'search', 'find'
        }
        
        # 复杂任务关键词
        self.complex_keywords = {
            '分析', '设计', '实现', '开发', '重构', '优化', '集成', '部署',
            '测试', '调试', '修复', '创建', '生成', '构建', '配置',
            'analyze', 'design', 'implement', 'develop', 'refactor', 'optimize',
            'integrate', 'deploy', 'test', 'debug', 'fix', 'create', 'build'
        }
        
        # 技术栈关键词
        self.tech_stack_keywords = {
            'database', 'api', 'microservice', 'docker', 'kubernetes',
            'ci/cd', 'react', 'vue', 'angular', 'node.js', 'python', 'java',
            '数据库', '接口', '微服务', '容器', '持续集成', '前端', '后端'
        }
        
        # 步骤指示词
        self.step_indicators = [
            r'然后.*?([，。]|\n)',      # 然后...
            r'接着.*?([，。]|\n)',      # 接着...
            r'之后.*?([，。]|\n)',      # 之后...
            r'最后.*?([，。]|\n)',      # 最后...
            r'首先.*?([，。]|\n)',      # 首先...
            r'第一步.*?([，。]|\n)',    # 第一步...
            r'第二.*?([，。]|\n)',      # 第二...
            r'.*?并.*?([，。]|\n)',     # A并B
            r'.*?同时.*?([，。]|\n)',   # A同时B
        ]
        
        # 不确定性指示词
        self.uncertainty_indicators = [
            '可能', '或许', '大概', '可能需要', '考虑',
            'maybe', 'possibly', 'probably', 'might need', 'consider'
        ]
    
    def analyze_task_complexity(self, user_text: str) -> TaskComplexityResult:
        """
        分析任务复杂度
        """
        text_lower = user_text.lower()
        original_text = user_text
        
        # 1. 计算各维度得分
        scores = {}
        factors = []
        
        # 关键词数量得分
        simple_count = sum(1 for kw in self.simple_keywords if kw in text_lower)
        complex_count = sum(1 for kw in self.complex_keywords if kw in text_lower)
        keyword_score = (complex_count * 2 - simple_count * 1) / 10
        scores['keyword_count'] = max(-1, min(1, keyword_score))
        
        if complex_count > simple_count:
            factors.append(f"包含{complex_count}个复杂操作关键词")
        
        # 步骤指示词得分
        step_count = sum(1 for pattern in self.step_indicators 
                        if re.search(pattern, original_text))
        step_score = min(step_count * 0.3, 1.0)
        scores['step_indicators'] = step_score
        
        if step_count > 0:
            factors.append(f"检测到{step_count}个步骤指示词")
        
        # 技术栈复杂度得分
        tech_count = sum(1 for kw in self.tech_stack_keywords if kw in text_lower)
        tech_score = min(tech_count * 0.2, 1.0)
        scores['technical_stack'] = tech_score
        
        if tech_count > 0:
            factors.append(f"涉及{tech_count}个技术栈组件")
        
        # 文本长度得分
        text_length = len(original_text)
        if text_length < 20:
            length_score = -0.5
        elif text_length < 50:
            length_score = 0
        elif text_length < 100:
            length_score = 0.3
        else:
            length_score = 0.6
        scores['text_length'] = length_score
        
        if text_length > 100:
            factors.append("任务描述较详细，可能包含多个要求")
        
        # 不确定性得分
        uncertainty_count = sum(1 for indicator in self.uncertainty_indicators 
                               if indicator in text_lower)
        uncertainty_score = uncertainty_count * 0.2
        scores['uncertainty'] = uncertainty_score
        
        if uncertainty_count > 0:
            factors.append(f"包含{uncertainty_count}个不确定性表述")
        
        # 依赖关系得分
        dependency_patterns = [r'依赖.*?([，。]|\n)', r'需要.*?之前.*?([，。]|\n)']
        dep_count = sum(1 for pattern in dependency_patterns 
                       if re.search(pattern, original_text))
        dep_score = min(dep_count * 0.3, 1.0)
        scores['dependencies'] = dep_score
        
        if dep_count > 0:
            factors.append(f"检测到{dep_count}个依赖关系")
        
        # 2. 计算综合得分
        total_score = sum(scores[key] * self.weights[key] for key in scores)
        
        # 3. 确定复杂度等级
        if total_score < -0.3:
            level = TaskComplexityLevel.SIMPLE
            confidence = min(abs(total_score) + 0.7, 1.0)
        elif total_score < 0.3:
            level = TaskComplexityLevel.MODERATE
            confidence = 0.7
        elif total_score < 0.7:
            level = TaskComplexityLevel.COMPLEX
            confidence = total_score + 0.3
        else:
            level = TaskComplexityLevel.ADVANCED
            confidence = min(total_score, 1.0)
        
        # 4. 估算步骤数
        estimated_steps = max(1, int(step_count + complex_count * 0.8 + tech_count * 0.5))
        
        # 5. 建议处理方式
        approach_suggestions = {
            TaskComplexityLevel.SIMPLE: "直接执行，无需规划",
            TaskComplexityLevel.MODERATE: "简单规划，2-3个步骤",
            TaskComplexityLevel.COMPLEX: "详细规划，需要分解任务",
            TaskComplexityLevel.ADVANCED: "架构设计，分阶段实施"
        }
        
        suggested_approach = approach_suggestions[level]
        
        return TaskComplexityResult(
            level=level,
            confidence=confidence,
            factors=factors,
            estimated_steps=estimated_steps,
            suggested_approach=suggested_approach
        )
    
    def get_intent_adjustment(self, complexity_result: TaskComplexityResult, 
                            original_intent: str, original_confidence: float) -> Tuple[str, float]:
        """
        根据复杂度调整意图分类
        """
        # 如果是高复杂度任务但被分类为GENERAL_CHAT，需要调整
        if (complexity_result.level in [TaskComplexityLevel.COMPLEX, TaskComplexityLevel.ADVANCED] and
            original_intent == "GENERAL_CHAT"):
            
            # 根据因素推断更合适的意图
            if any("技术栈" in factor or "架构" in factor for factor in complexity_result.factors):
                return "PROJECT_DESIGN", min(original_confidence + 0.3, 1.0)
            elif any("开发" in factor or "实现" in factor for factor in complexity_result.factors):
                return "CODING_TASK", min(original_confidence + 0.4, 1.0)
            elif any("分析" in factor for factor in complexity_result.factors):
                return "REPO_ANALYSIS", min(original_confidence + 0.3, 1.0)
        
        # 如果是简单任务但被分类为复杂意图，也可以调整
        if (complexity_result.level == TaskComplexityLevel.SIMPLE and
            original_intent not in ["GENERAL_CHAT", "CAPABILITY_QUERY"] and
            original_confidence < 0.8):
            
            return "GENERAL_CHAT", max(original_confidence - 0.2, 0.5)
        
        return original_intent, original_confidence

# 测试用例
def test_complexity_analyzer():
    """测试复杂度分析器"""
    analyzer = TaskComplexityAnalyzer()
    
    test_cases = [
        ("列出当前目录的文件", "SIMPLE"),
        ("分析代码结构并生成报告，然后重构数据库接口", "COMPLEX"),
        ("设计一个微服务架构，包括API网关、认证服务和数据处理管道", "ADVANCED"),
        ("修复登录页面的CSS样式问题", "MODERATE"),
        ("你好", "SIMPLE"),
        ("实现用户注册功能，包括数据库设计、API开发、前端界面和测试", "ADVANCED"),
        ("读取README文件内容", "SIMPLE"),
        ("优化数据库查询性能并添加缓存机制", "COMPLEX"),
    ]
    
    print("任务复杂度分析测试:")
    print("-" * 60)
    
    for text, expected_level in test_case
