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
    意图分类器：使用 LLM 对用户输入进行语义分类。
    规范化：这是决策门（Decision Gate）的前置步骤。
    """
    
    
   

    def __init__(self, llm_client: Any, file_only_logger: Any = None):
        self.llm = llm_client
        self.file_only_logger = file_only_logger
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

    def classify(self, user_text: str) -> ClassificationResult:
        """执行分类。"""
        # 1) 业界做法：对极短/高频“闲聊/能力询问”走启发式，避免不必要的大模型请求。
        # 这样能显著提升健壮性：当本地 llama.cpp 不可用时，仍可正常回应问候/说明能力。
        text_strip = (user_text or "").strip().lower()
        # if not text_strip:
        #     return ClassificationResult(category=IntentCategory.GENERAL_CHAT, reason="Heuristic: empty input", confidence=1.0)

        # greetings = {
        #     "你好", "你好啊", "您好", "哈喽", "嗨", "hi", "hello", "hey",
        #     "在吗", "在不在", "晚安", "早上好", "下午好", "晚上好",
        # }
        # if text_strip in greetings:
        #     return ClassificationResult(category=IntentCategory.GENERAL_CHAT, reason="Heuristic: greeting", confidence=1.0)

        # # 一些常见“寒暄 + 标点”的变体（例如：你好啊～/你好啊!!）
        # if len(text_strip) <= 8 and any(k in text_strip for k in ("你好", "哈喽", "嗨", "hi", "hello")):
        #     return ClassificationResult(category=IntentCategory.GENERAL_CHAT, reason="Heuristic: greeting (variant)", confidence=0.95)

        # if any(kw in text_strip for kw in ("你可以干嘛", "能干嘛", "怎么用", "帮助", "help", "capability", "can you")):
        #     return ClassificationResult(category=IntentCategory.CAPABILITY_QUERY, reason="Heuristic: capability keyword", confidence=0.95)

        # 走 LLM 深度语义分类
        from clude_code.llm.llama_cpp_http import ChatMessage
        try:
            # 转义用户输入中的花括号，避免 format() 解析错误
            # safe_user_text = self._escape_for_format(user_text)
            prompt = _render_prompt(
                                "user/stage/intent_classify.j2", 
                                user_text=user_text,
                                )
            if self.file_only_logger:   
                self.file_only_logger.info("====>意图分类器输入 Prompt: %s", prompt)

            response = self.llm.chat([ChatMessage(role="user", content=prompt)])
            
            # 打印返回 JSON 到文件（不输出到屏幕）
            if self.file_only_logger:
                # 1. 长度截断保护（防止极端情况内存溢出）
                # safe_resp = response[:10000] + ("..." if len(response) > 10000 else "")
                self.file_only_logger.info("====>意图分类器返回数据 Response: %s", response);
            
            # 容错提取 JSON
            json_match = re.search(r"(\{.*?\})", response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(1))
                return ClassificationResult.model_validate(data)
        except Exception as e:
            # 异常只写入文件：不打印到屏幕（避免污染 live UI / 避免 Typer 输出 traceback）
            if self.file_only_logger:
                # 注意：这里不要 f-string 拼接超长内容；只记录关键信息 + 截断后的输入
                self.file_only_logger.exception(
                    "IntentClassifier LLM 分类失败（将返回 UNCERTAIN）。user_text=%r ",
                    (user_text[:500] + "…") if len(user_text) > 500 else user_text, 
                    exc_info=True,
                )
            
        return ClassificationResult(category=IntentCategory.UNCERTAIN, reason="Fallback to default")

