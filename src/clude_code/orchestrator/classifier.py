from __future__ import annotations
import json
import re
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from clude_code.prompts import render_prompt as _render_prompt

# class UserIntent:
#     # 核心功能类
#     CODING_TASK = "CODING_TASK"           # 写、改、重构、测试代码
#     ERROR_DIAGNOSIS = "ERROR_DIAGNOSIS"   # 分析错误信息，调试
#     REPO_ANALYSIS = "REPO_ANALYSIS"       # 分析用户代码仓库：解释、搜素、找入口
#     DOCUMENTATION_TASK = "DOCUMENTATION_TASK" # 生成或解释文档、注释

#     # 咨询与规划类
#     TECHNICAL_CONSULTING = "TECHNICAL_CONSULTING" # 解释概念、原理、最佳实践
#     PROJECT_DESIGN = "PROJECT_DESIGN"     # 架构设计、技术选型
#     SECURITY_CONSULTING = "SECURITY_CONSULTING" # 安全相关咨询

#     # 元交互类
#     CAPABILITY_QUERY = "CAPABILITY_QUERY" # 询问助手能力、使用方法
#     GENERAL_CHAT = "GENERAL_CHAT"         # 问候、致谢等基础社交
#     CASUAL_CHAT = "CASUAL_CHAT"           # 开放式闲聊、征求意见

#     # 兜底类
#     UNCERTAIN = "UNCERTAIN"               # 意图模糊，无法归类

# IntentCategory 已迁移到 registry/intent_registry.py，这里导入使用
from clude_code.orchestrator.registry.intent_registry import IntentCategory

class ClassificationResult(BaseModel):
    """分类结果。"""
    category: IntentCategory
    reason: str = Field("", description="分类理由")
    confidence: float = Field(1.0, ge=0.0, le=1.0)

class IntentClassifier:
    """
    意图分类器：使用关键词 + LLM 混合策略对用户输入进行语义分类。
    
    P1-4 业界对标：
    - 快速路径：关键词匹配（高置信度直接返回）
    - 精准路径：LLM 深度语义分类（低置信度时使用）
    
    规范化：这是决策门（Decision Gate）的前置步骤。
    """
    
    # P1-4: 关键词分类规则
    _KEYWORD_RULES: list[tuple[IntentCategory, set[str], float]] = [
        # (意图类型, 关键词集合, 置信度)
        
        # 问候类 - 高置信度
        (IntentCategory.GENERAL_CHAT, {
            "你好", "你好啊", "您好", "哈喽", "嗨", "hi", "hello", "hey",
            "在吗", "在不在", "晚安", "早上好", "下午好", "晚上好",
            "谢谢", "感谢", "辛苦了", "拜拜", "再见"
        }, 0.98),
        
        # 能力询问类
        (IntentCategory.CAPABILITY_QUERY, {
            "你可以干嘛", "能干嘛", "怎么用", "帮助", "help", "capability",
            "can you", "你会什么", "你能做什么", "有什么功能"
        }, 0.95),
        
        # 编码任务类
        (IntentCategory.CODING_TASK, {
            "写代码", "修改代码", "重构", "优化代码", "实现", "添加功能",
            "fix bug", "修复", "implement", "create function", "add feature"
        }, 0.85),
        
        # 错误诊断类
        (IntentCategory.ERROR_DIAGNOSIS, {
            "报错", "error", "bug", "调试", "debug", "失败", "异常",
            "traceback", "exception", "为什么不工作", "doesn't work"
        }, 0.85),
        
        # 仓库分析类
        (IntentCategory.REPO_ANALYSIS, {
            "分析代码", "解释代码", "这段代码", "代码结构", "入口在哪",
            "explain", "analyze", "what does this", "找一下"
        }, 0.80),
        
        # 文档任务类
        (IntentCategory.DOCUMENTATION_TASK, {
            "写文档", "生成文档", "添加注释", "readme", "docstring",
            "document", "写注释"
        }, 0.85),
        
        # 技术咨询类
        (IntentCategory.TECHNICAL_CONSULTING, {
            "什么是", "解释一下", "原理是什么", "最佳实践", "怎么理解",
            "what is", "how does", "explain", "best practice"
        }, 0.75),
        
        # 项目设计类
        (IntentCategory.PROJECT_DESIGN, {
            "架构设计", "技术选型", "系统设计", "设计方案", "architecture",
            "design", "技术栈"
        }, 0.80),
        
        # 安全咨询类
        (IntentCategory.SECURITY_CONSULTING, {
            "安全", "漏洞", "security", "vulnerability", "xss", "sql注入",
            "加密", "认证"
        }, 0.85),
    ]
    
    # P1-4: 关键词分类置信度阈值（低于此值走 LLM）
    _KEYWORD_CONFIDENCE_THRESHOLD = 0.90

    def __init__(self, llm_client: Any, file_only_logger: Any = None):
        self.llm = llm_client
        self.file_only_logger = file_only_logger
        self._last_category: IntentCategory | None = None  # 记录最后分类结果
        # 新结构：user/stage/intent_classify.j2

    @staticmethod
    def _escape_for_format(s: str) -> str:
        """
        修复 str.format 的花括号陷阱：
        user_text 如果包含 '{' / '}'（例如 JSON、patch、模板字符串），
        prompt.format(user_text=...) 会把它误当成占位符并抛异常。
        解决方案：转义所有花括号（{ -> {{, } -> }}）
        """
        return (s or "").replace("{", "{{").replace("}", "}}")
    
    def _keyword_classify(self, text: str) -> ClassificationResult | None:
        """
        P1-4: 关键词快速分类。
        
        返回:
            ClassificationResult 如果匹配成功，None 如果未匹配
        """
        text_lower = text.strip().lower()
        
        if not text_lower:
            return ClassificationResult(
                category=IntentCategory.GENERAL_CHAT,
                reason="Heuristic: empty input",
                confidence=1.0
            )
        
        # 精确匹配问候语
        greetings = {"你好", "你好啊", "您好", "哈喽", "嗨", "hi", "hello", "hey"}
        if text_lower in greetings:
            return ClassificationResult(
                category=IntentCategory.GENERAL_CHAT,
                reason="Heuristic: exact greeting match",
                confidence=0.99
            )
        
        # 短文本问候变体
        if len(text_lower) <= 10 and any(k in text_lower for k in ("你好", "哈喽", "嗨", "hi", "hello")):
            return ClassificationResult(
                category=IntentCategory.GENERAL_CHAT,
                reason="Heuristic: greeting variant",
                confidence=0.95
            )
        
        # 遍历关键词规则
        best_match: tuple[IntentCategory, float, str] | None = None
        for category, keywords, base_confidence in self._KEYWORD_RULES:
            for kw in keywords:
                if kw in text_lower:
                    # 计算匹配置信度（关键词越长越可信）
                    confidence = base_confidence * (1 + len(kw) / 50)
                    confidence = min(confidence, 0.99)
                    
                    if best_match is None or confidence > best_match[1]:
                        best_match = (category, confidence, kw)
        
        if best_match:
            return ClassificationResult(
                category=best_match[0],
                reason=f"Heuristic: keyword '{best_match[2]}'",
                confidence=best_match[1]
            )
        
        return None

    def classify(self, user_text: str) -> ClassificationResult:
        """
        执行混合分类（关键词 + LLM）。
        
        P1-4 策略：
        1. 先尝试关键词分类
        2. 高置信度（>= 0.90）直接返回
        3. 低置信度或无匹配时走 LLM
        """
        text_strip = (user_text or "").strip()
        
        # P1-4: 第一步 - 关键词快速分类
        keyword_result = self._keyword_classify(text_strip)
        
        if keyword_result:
            # 高置信度直接返回（快速路径）
            if keyword_result.confidence >= self._KEYWORD_CONFIDENCE_THRESHOLD:
                if self.file_only_logger:
                    self.file_only_logger.info(
                        "====>关键词分类命中（快速路径）: %s, 置信度: %.2f, 原因: %s",
                        keyword_result.category.value,
                        keyword_result.confidence,
                        keyword_result.reason
                    )
                self._last_category = keyword_result.category
                return keyword_result
            
            # 低置信度作为备选
            if self.file_only_logger:
                self.file_only_logger.info(
                    "====>关键词分类低置信度，走 LLM: %s, 置信度: %.2f",
                    keyword_result.category.value,
                    keyword_result.confidence
                )

        # P1-4: 第二步 - LLM 深度语义分类
        from clude_code.llm.llama_cpp_http import ChatMessage
        try:
            prompt = _render_prompt(
                "user/stage/intent_classify.j2", 
                user_text=user_text,
            )
            if self.file_only_logger:   
                self.file_only_logger.info("====>意图分类器输入 Prompt: %s", prompt)

            response = self.llm.chat([ChatMessage(role="user", content=prompt)])
            
            if self.file_only_logger:
                self.file_only_logger.info("====>意图分类器返回数据 Response: %s", response)
            
            # 容错提取 JSON
            json_match = re.search(r"(\{.*?\})", response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(1))
                llm_result = ClassificationResult.model_validate(data)
                
                # P1-4: 融合关键词和 LLM 结果
                if keyword_result and keyword_result.category == llm_result.category:
                    # 两者一致，提升置信度
                    llm_result.confidence = min(llm_result.confidence + 0.1, 1.0)
                    llm_result.reason = f"Hybrid: {keyword_result.reason} + LLM"
                
                self._last_category = llm_result.category
                return llm_result
                
        except Exception as e:
            # 异常只写入文件
            if self.file_only_logger:
                self.file_only_logger.exception(
                    "IntentClassifier LLM 分类失败。user_text=%r ",
                    (user_text[:500] + "…") if len(user_text) > 500 else user_text, 
                    exc_info=True,
                )
            
            # P1-4: LLM 失败时使用关键词结果作为兜底
            if keyword_result:
                if self.file_only_logger:
                    self.file_only_logger.info(
                        "====>LLM 失败，降级使用关键词结果: %s",
                        keyword_result.category.value
                    )
                self._last_category = keyword_result.category
                return keyword_result
        
        # 兜底返回
        self._last_category = IntentCategory.UNCERTAIN
        return ClassificationResult(category=IntentCategory.UNCERTAIN, reason="Fallback to default")

