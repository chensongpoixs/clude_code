"""
Claude Code标准压缩算法模块

实现多种压缩策略，确保在不同场景下的最优token管理
"""
from typing import List, Dict, Any, Optional, Tuple
import time
import re

from ...llm.http_client import ChatMessage
from ..core.constants import (
    ContextPriority, 
    ClaudeContextItem, 
    CompressionResult,
    ClaudeCodeConstants
)
from ..utils.token import get_token_calculator
from ..utils.content import get_content_normalizer


class CompressionEngine:
    """Claude Code标准压缩引擎
    
    提供多层次压缩策略：
    1. 轻度压缩：保留关键信息，轻微截断
    2. 中度压缩：智能摘要，保留结构
    3. 重度压缩：最小化表示，保留核心
    4. 紧急压缩：极致压缩，仅保留标识
    """
    
    def __init__(self):
        self.token_calculator = get_token_calculator()
        self.content_normalizer = get_content_normalizer()
        self.compression_history: List[Dict[str, Any]] = []
    
    def compress_item(self, item: ClaudeContextItem, 
                   max_tokens: int,
                   compression_level: str = "auto") -> CompressionResult:
        """
        压缩单个上下文项
        
        参数:
            item: 要压缩的上下文项
            max_tokens: 最大允许的token数
            compression_level: 压缩级别 (light/medium/heavy/emergency/auto)
        
        返回:
            CompressionResult: 压缩结果
        """
        if not item.can_compress():
            return CompressionResult(
                success=False,
                original_tokens=item.calculate_tokens(),
                compressed_tokens=item.calculate_tokens(),
                algorithm_used="not_compressible"
            )
        
        original_tokens = item.calculate_tokens(self.token_calculator.encoding_name)
        
        # 自动选择压缩级别
        if compression_level == "auto":
            compression_level = self._select_compression_level(original_tokens, max_tokens)
        
        # 执行对应压缩策略
        if compression_level == "light":
            return self._light_compression(item, max_tokens)
        elif compression_level == "medium":
            return self._medium_compression(item, max_tokens)
        elif compression_level == "heavy":
            return self._heavy_compression(item, max_tokens)
        elif compression_level == "emergency":
            return self._emergency_compression(item)
        else:
            return CompressionResult(success=False, original_tokens=original_tokens)
    
    def compress_batch(self, items: List[ClaudeContextItem], 
                     max_total_tokens: int,
                     preserve_count: int = 0) -> Tuple[List[ClaudeContextItem], CompressionResult]:
        """批量压缩多个项目"""
        if not items:
            return items, CompressionResult(success=False)
        
        # 计算当前总token
        current_tokens = sum(item.calculate_tokens(self.token_calculator.encoding_name) 
                             for item in items)
        
        if current_tokens <= max_total_tokens:
            return items, CompressionResult(success=True)
        
        # 保留前N个高优先级项目
        if preserve_count > 0 and len(items) > preserve_count:
            preserved_items = items[:preserve_count]
            remaining_items = items[preserve_count:]
            remaining_tokens = max_total_tokens - sum(
                item.calculate_tokens(self.token_calculator.encoding_name) 
                for item in preserved_items
            )
            
            compressed_remaining, result = self._compress_batch_with_limit(
                remaining_items, remaining_tokens
            )
            
            final_items = preserved_items + compressed_remaining
            total_result = CompressionResult(
                success=result.success,
                original_tokens=current_tokens,
                compressed_tokens=sum(item.calculate_tokens(self.token_calculator.encoding_name) 
                                     for item in final_items),
                algorithm_used=f"batch_preserve_{preserve_count}"
            )
            return final_items, total_result
        else:
            return self._compress_batch_with_limit(items, max_total_tokens)
    
    def _select_compression_level(self, original_tokens: int, max_tokens: int) -> str:
        """自动选择压缩级别"""
        compression_ratio = max_tokens / max(1, original_tokens)
        
        if compression_ratio >= 0.8:
            return "light"      # 轻度压缩：保留80%+
        elif compression_ratio >= 0.5:
            return "medium"     # 中度压缩：保留50-80%
        elif compression_ratio >= 0.2:
            return "heavy"       # 重度压缩：保留20-50%
        else:
            return "emergency"   # 紧急压缩：保留<20%
    
    def _light_compression(self, item: ClaudeContextItem, max_tokens: int) -> CompressionResult:
        """轻度压缩：保留大部分内容"""
        content = item.content
        original_tokens = item.calculate_tokens(self.token_calculator.encoding_name)
        
        # 策略1：移除多余空白
        optimized_content = re.sub(r'\s+', ' ', content.strip())
        
        # 策略2：移除重复换行
        optimized_content = re.sub(r'\n{3,}', '\n\n', optimized_content)
        
        # 策略3：如果仍超限，智能截断
        if self.token_calculator.calculate_tokens(optimized_content) > max_tokens:
            try:
                encoding = self.token_calculator.get_encoding()
                tokens = encoding.encode(optimized_content)
                if len(tokens) > max_tokens:
                    # 保留前90%的内容
                    keep_tokens = int(max_tokens * 0.9)
                    truncated = encoding.decode(tokens[:keep_tokens]) + " [截断]"
                    optimized_content = truncated
            except:
                # 降级到字符截断
                char_limit = int(max_tokens * 1.2)  # 粗略估算
                optimized_content = optimized_content[:char_limit] + " [截断]"
        
        compressed_tokens = self.token_calculator.calculate_tokens(optimized_content)
        
        return CompressionResult(
            success=True,
            original_tokens=original_tokens,
            compressed_tokens=compressed_tokens,
            compression_ratio=1 - (compressed_tokens / max(1, original_tokens)),
            algorithm_used="light_compression",
            quality_score=self._calculate_quality_score(original_tokens, compressed_tokens)
        )
    
    def _medium_compression(self, item: ClaudeContextItem, max_tokens: int) -> CompressionResult:
        """中度压缩：智能摘要"""
        content = item.content
        original_tokens = item.calculate_tokens(self.token_calculator.encoding_name)
        
        # 策略1：提取关键句子
        sentences = re.split(r'[.!?。！？]', content)
        key_sentences = []
        
        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) > 10:  # 保留有意义的句子
                key_sentences.append(sentence)
        
        # 策略2：按重要性排序（前面和后面的更重要）
        if len(key_sentences) > 3:
            # 保留前2个和后1个
            key_sentences = key_sentences[:2] + [key_sentences[-1]]
        elif len(key_sentences) > 1:
            # 保留第一个
            key_sentences = [key_sentences[0]]
        
        optimized_content = '。'.join(key_sentences)
        
        # 策略3：添加压缩标识
        if len(key_sentences) < len(sentences):
            optimized_content += f"\n\n[摘要：已从{len(sentences)}句中提取{len(key_sentences)}句关键信息]"
        
        # 策略4：长度控制
        if self.token_calculator.calculate_tokens(optimized_content) > max_tokens:
            optimized_content = self._truncate_to_token_limit(optimized_content, max_tokens)
        
        compressed_tokens = self.token_calculator.calculate_tokens(optimized_content)
        
        return CompressionResult(
            success=True,
            original_tokens=original_tokens,
            compressed_tokens=compressed_tokens,
            compression_ratio=1 - (compressed_tokens / max(1, original_tokens)),
            algorithm_used="medium_compression",
            quality_score=self._calculate_quality_score(original_tokens, compressed_tokens)
        )
    
    def _heavy_compression(self, item: ClaudeContextItem, max_tokens: int) -> CompressionResult:
        """重度压缩：最小化表示"""
        content = item.content
        original_tokens = item.calculate_tokens(self.token_calculator.encoding_name)
        
        # 策略1：提取关键词
        words = re.findall(r'\b\w{2,}\b', content.lower())
        key_words = list(set(words[:10]))  # 最多10个关键词
        
        # 策略2：识别内容类型
        content_type = self._identify_content_type(content)
        
        # 策略3：生成最小化表示
        if content_type == "code":
            optimized_content = f"[代码片段] {'; '.join(key_words[:5])}"
        elif content_type == "list":
            optimized_content = f"[列表] {'; '.join(key_words[:5])}"
        elif content_type == "dialogue":
            optimized_content = f"[对话] {'; '.join(key_words[:3])}"
        else:
            optimized_content = f"[{content_type}] {'; '.join(key_words[:5])}"
        
        # 策略4：长度控制
        if self.token_calculator.calculate_tokens(optimized_content) > max_tokens:
            optimized_content = self._truncate_to_token_limit(optimized_content, max_tokens)
        
        compressed_tokens = self.token_calculator.calculate_tokens(optimized_content)
        
        return CompressionResult(
            success=True,
            original_tokens=original_tokens,
            compressed_tokens=compressed_tokens,
            compression_ratio=1 - (compressed_tokens / max(1, original_tokens)),
            algorithm_used="heavy_compression",
            quality_score=self._calculate_quality_score(original_tokens, compressed_tokens)
        )
    
    def _emergency_compression(self, item: ClaudeContextItem) -> CompressionResult:
        """紧急压缩：极致压缩"""
        original_tokens = item.calculate_tokens(self.token_calculator.encoding_name)
        
        # 紧急策略：仅保留类型标识
        if item.category == "system":
            optimized_content = "[系统消息]"
        elif item.category == "tool_result":
            tool_name = item.metadata.get("tool_name", "工具")
            optimized_content = f"[{tool_name}]完成"
        elif item.category in ["assistant", "user"]:
            optimized_content = f"[{item.category}]"
        elif item.category == "tool_call":
            optimized_content = "[工具调用]"
        else:
            optimized_content = f"[{item.category}]"
        
        compressed_tokens = self.token_calculator.calculate_tokens(optimized_content)
        
        return CompressionResult(
            success=True,
            original_tokens=original_tokens,
            compressed_tokens=compressed_tokens,
            compression_ratio=1 - (compressed_tokens / max(1, original_tokens)),
            algorithm_used="emergency_compression",
            quality_score=self._calculate_quality_score(original_tokens, compressed_tokens)
        )
    
    def _compress_batch_with_limit(self, items: List[ClaudeContextItem], 
                                     max_tokens: int) -> Tuple[List[ClaudeContextItem], CompressionResult]:
        """批量压缩到指定token限制"""
        if not items:
            return items, CompressionResult(success=False)
        
        compressed_items = []
        used_tokens = 0
        compression_results = []
        
        # 按优先级排序
        sorted_items = sorted(items, 
                               key=lambda x: (-x.priority.value, -x.created_at))
        
        for item in sorted_items:
            remaining_tokens = max_tokens - used_tokens
            
            if remaining_tokens <= 0:
                break
            
            # 压缩当前项目
            result = self.compress_item(item, remaining_tokens)
            compression_results.append(result)
            
            if result.success:
                # 创建压缩后的项目
                compressed_item = ClaudeContextItem(
                    content=result.algorithm_used + ": " + (result.compressed_content or ""),
                    priority=item.priority,
                    category=item.category + "_compressed",
                    metadata={
                        **item.metadata,
                        "compression_result": result.to_summary()
                    },
                    compressed=True
                )
                compressed_items.append(compressed_item)
                used_tokens += result.compressed_tokens
            else:
                break
        
        # 计算总结果
        original_total = sum(item.calculate_tokens(self.token_calculator.encoding_name) 
                            for item in items)
        compressed_total = sum(result.compressed_tokens for result in compression_results)
        
        batch_result = CompressionResult(
            success=len(compressed_items) > 0,
            original_tokens=original_total,
            compressed_tokens=compressed_total,
            compression_ratio=1 - (compressed_total / max(1, original_total)),
            algorithm_used="batch_compression",
            quality_score=self._calculate_quality_score(original_total, compressed_total)
        )
        
        return compressed_items, batch_result
    
    def _identify_content_type(self, content: str) -> str:
        """识别内容类型"""
        content_lower = content.lower()
        
        # 代码特征
        if (re.search(r'\b(def|class|function|import|export|const|let|var)\b', content_lower) or
            re.search(r'[{}[\];', content) or
            re.search(r'function\s+\w+\s*\(', content_lower)):
            return "code"
        
        # 列表特征
        if (re.search(r'^\s*[-*•+]\s+', content_lower) or
            re.search(r'^\s*\d+\.\s+', content_lower)):
            return "list"
        
        # 对话特征
        if re.search(r'(我|你|他|她|它)', content_lower):
            return "dialogue"
        
        return "text"
    
    def _truncate_to_token_limit(self, content: str, max_tokens: int) -> str:
        """截断到token限制"""
        try:
            encoding = self.token_calculator.get_encoding()
            tokens = encoding.encode(content)
            if len(tokens) <= max_tokens:
                return content
            else:
                truncated = encoding.decode(tokens[:max_tokens])
                return truncated + " [截断]"
        except:
            # 降级到字符截断
            char_limit = int(max_tokens * 1.2)
            return content[:char_limit] + " [截断]"
    
    def _calculate_quality_score(self, original: int, compressed: int) -> float:
        """计算压缩质量评分"""
        if original == 0:
            return 0.0
        
        # 基于压缩率的质量评分
        compression_ratio = compressed / max(1, original)
        
        if compression_ratio >= 0.9:
            return 0.95  # 几乎无损
        elif compression_ratio >= 0.7:
            return 0.85  # 轻微压缩
        elif compression_ratio >= 0.4:
            return 0.70  # 中度压缩
        else:
            return 0.50  # 重度压缩
    
    def get_compression_stats(self) -> Dict[str, Any]:
        """获取压缩统计"""
        if not self.compression_history:
            return {"total_compressions": 0}
        
        total = len(self.compression_history)
        successful = sum(1 for record in self.compression_history if record.get("success", False))
        
        # 计算平均效率
        avg_efficiency = 0.0
        if successful > 0:
            total_efficiency = sum(record.get("efficiency_score", 0) 
                                    for record in self.compression_history)
            avg_efficiency = total_efficiency / successful
        
        return {
            "total_compressions": total,
            "successful_compressions": successful,
            "success_rate": successful / max(1, total),
            "average_efficiency": avg_efficiency,
            "recent_history": self.compression_history[-10:]  # 最近10次记录
        }
    
    def record_compression(self, result: CompressionResult, item_info: Dict[str, Any]) -> None:
        """记录压缩结果"""
        record = {
            **result.to_summary(),
            "item_info": item_info,
            "timestamp": time.time(),
            "efficiency_score": result.efficiency_score
        }
        self.compression_history.append(record)
        
        # 保持历史记录在合理范围
        if len(self.compression_history) > 1000:
            self.compression_history = self.compression_history[-500:]


# 全局压缩引擎实例
_compression_engine: Optional[CompressionEngine] = None

def get_compression_engine() -> CompressionEngine:
    """获取压缩引擎实例"""
    global _compression_engine
    if _compression_engine is None:
        _compression_engine = CompressionEngine()
    return _compression_engine