#!/usr/bin/env python3
"""
意图识别器修复方案
解决复杂工作流任务被错误归类为GENERAL_CHAT的问题
"""

# 修复1: 扩展编码任务关键词，提高复杂任务识别能力
CODING_TASK_KEYWORDS_ENHANCED = {
    # 原有关键词
    "写代码", "修改代码", "重构", "优化代码", "实现", "添加功能",
    "fix bug", "修复", "implement", "create function", "add feature",
    
    # 新增复杂工作流关键词
    "分析代码结构", "生成报告", "模块设计", "架构重构", "接口开发",
    "数据库设计", "性能优化", "安全加固", "单元测试", "集成测试",
    "代码审查", "部署配置", "CI/CD", "工作流", "管道", "自动化",
    "微服务", "API开发", "前端组件", "后端服务", "数据处理",
    "批量处理", "系统监控", "日志分析", "错误追踪", "版本管理",
    "依赖管理", "包管理", "环境配置", "Docker", "Kubernetes",
    "代码生成", "模板引擎", "数据迁移", "缓存策略", "消息队列"
}

# 修复2: 提高编码任务分类的置信度
CODING_TASK_CONFIDENCE = 0.92  # 从0.85提高到0.92

# 修复3: 增加任务复杂度判断逻辑
COMPLEX_TASK_PATTERNS = [
    "分析.*并.*",  # 分析A并B
    "设计.*实现",  # 设计A实现B
    "重构.*优化",  # 重构A优化B
    "开发.*测试",  # 开发A测试B
    "创建.*部署",  # 创建A部署B
    "集成.*验证",  # 集成A验证B
    "迁移.*同步",  # 迁移A同步B
]

# 修复4: 降低关键词分类阈值，让更多任务走LLM精确分类
KEYWORD_CONFIDENCE_THRESHOLD = 0.88  # 从0.90降低到0.88

# 修复5: 增加复杂度评估函数
def evaluate_task_complexity(user_text: str) -> float:
    """
    评估任务复杂度，返回0-1之间的值
    考虑因素：关键词数量、步骤数、涉及的技术栈等
    """
    complexity_score = 0.0
    text_lower = user_text.lower()
    
    # 1. 关键词数量得分
    complex_keywords_found = sum(1 for kw in CODING_TASK_KEYWORDS_ENHANCED if kw in text_lower)
    complexity_score += min(complex_keywords_found * 0.1, 0.4)
    
    # 2. 多步骤模式得分
    for pattern in COMPLEX_TASK_PATTERNS:
        import re
        if re.search(pattern, text_lower):
            complexity_score += 0.2
            break
    
    # 3. 技术栈关键词得分
    tech_keywords = ["数据库", "API", "微服务", "Docker", "CI/CD", "测试", "部署", "监控"]
    tech_found = sum(1 for kw in tech_keywords if kw in text_lower)
    complexity_score += min(tech_found * 0.1, 0.3)
    
    # 4. 长度得分（长文本通常更复杂）
    if len(user_text) > 50:
        complexity_score += 0.1
    
    return min(complexity_score, 1.0)

print("意图识别器修复方案已生成")
print(f"- 扩展编码任务关键词: {len(CODING_TASK_KEYWORDS_ENHANCED)} 个")
print(f"- 提高置信度到: {CODING_TASK_CONFIDENCE}")
print(f"- 降低阈值到: {KEYWORD_CONFIDENCE_THRESHOLD}")
