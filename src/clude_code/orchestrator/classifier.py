from __future__ import annotations
import json
import re
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

class IntentCategory(str, Enum):
    """用户意图分类标签。"""
    CODING_TASK = "CODING_TASK"           # 代码任务：修改、重构、写代码、跑测试、修复 bug
    CAPABILITY_QUERY = "CAPABILITY_QUERY" # 能力询问：你可以干嘛、怎么用、有哪些工具、你能帮我吗
    REPO_ANALYSIS = "REPO_ANALYSIS"       # 仓库分析：代码结构、逻辑解释、寻找入口、RAG 搜索
    GENERAL_CHAT = "GENERAL_CHAT"         # 通用对话：你好、谢谢、你是谁
    UNCERTAIN = "UNCERTAIN"               # 意图模糊

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
    
    CLASSIFY_PROMPT = """你是一个任务分类器。请根据用户的输入，将其分类到以下类别之一：
1. CODING_TASK: 涉及具体的代码编写、修改、测试、修复或文件操作。
2. CAPABILITY_QUERY: 询问你作为一个 AI 代理的能力、工具、用法或帮助说明。
3. REPO_ANALYSIS: 询问代码逻辑、架构分析、寻找特定功能的入口文件或进行 RAG 搜索。
4. GENERAL_CHAT: 简单的寒暄、问候或非技术性交流。

要求：
- 只输出严格的 JSON 对象，不要输出任何解释。
- 格式：{{"category": "类别名", "reason": "理由", "confidence": 0.9}}

用户输入：
"{user_text}"
"""

    def __init__(self, llm_client: Any, file_only_logger: Any = None):
        self.llm = llm_client
        self.file_only_logger = file_only_logger

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
            safe_user_text = self._escape_for_format(user_text)
            prompt = self.CLASSIFY_PROMPT.format(user_text=safe_user_text)
            if self.file_only_logger:   
                self.file_only_logger.info("====>意图分类器输入 Prompt: %s", prompt)

            response = self.llm.chat([ChatMessage(role="user", content=prompt)])
            
            # 打印返回 JSON 到文件（不输出到屏幕）
            if self.file_only_logger:
                # 1. 长度截断保护（防止极端情况内存溢出）
                safe_resp = response[:10000] + ("..." if len(response) > 10000 else "")
                self.file_only_logger.info("====>意图分类器返回数据 Response: %s", safe_resp)
            
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

