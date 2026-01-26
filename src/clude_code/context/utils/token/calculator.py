"""
Token计算工具

提供精确的token计算、估算和优化功能
"""
import tiktoken
from typing import Union, List, Dict, Any, Optional, Tuple
import re


class TokenCalculator:
    """Token计算器
    
    支持多种编码和优化策略
    """
    
    def __init__(self, encoding_name: str = "cl100k_base"):
        self.encoding_name = encoding_name
        self._encoding_cache: Dict[str, Any] = {}
        
    def get_encoding(self) -> Any:
        """获取编码器（带缓存）"""
        if self.encoding_name not in self._encoding_cache:
            try:
                self._encoding_cache[self.encoding_name] = tiktoken.get_encoding(self.encoding_name)
            except Exception as e:
                # 降级到基础编码
                self._encoding_cache[self.encoding_name] = tiktoken.get_encoding("cl100k_base")
        return self._encoding_cache[self.encoding_name]
    
    def calculate_tokens(self, text: str, use_cache: bool = True) -> int:
        """精确计算token数"""
        if not text:
            return 0
            
        # 尝试使用tiktoken精确计算
        try:
            encoding = self.get_encoding()
            return len(encoding.encode(text))
        except Exception:
            # 降级到估算方法
            return self.estimate_tokens(text)
    
    def estimate_tokens(self, text: str) -> int:
        """估算token数（降级方法）"""
        if not text:
            return 0
            
        # 中英文混合估算
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        chinese_punctuation = len(re.findall(r'[，。！？；：""''（）【】《》]', text))
        
        # 英文单词和字符
        english_content = re.sub(r'[\u4e00-\u9fff，。！？；：""''（）【】《》]', '', text)
        english_words = len(re.findall(r'\b\w+\b', english_content))
        english_chars = len(english_content) - len(' '.join(re.findall(r'\b\w+\b', english_content)))
        
        # 代码和特殊字符
        code_chars = len(re.findall(r'[{}[\]<>|\\`~]', text))
        
        # Token估算规则
        tokens = (
            chinese_chars * 1.5 +           # 中文字符 ≈ 1.5 tokens
            chinese_punctuation * 0.5 +       # 中文标点 ≈ 0.5 tokens
            english_words * 1.0 +           # 英文单词 ≈ 1.0 tokens
            english_chars * 0.5 +           # 英文字符 ≈ 0.5 tokens
            code_chars * 0.3                 # 代码字符 ≈ 0.3 tokens
        )
        
        return int(tokens)
    
    def calculate_batch_tokens(self, texts: List[str]) -> List[int]:
        """批量计算tokens"""
        return [self.calculate_tokens(text) for text in texts]
    
    def get_token_breakdown(self, text: str) -> Dict[str, Any]:
        """获取token分解详情"""
        if not text:
            return {"total_tokens": 0, "breakdown": {}}
        
        # 基础统计
        char_count = len(text)
        exact_tokens = self.calculate_tokens(text)
        estimated_tokens = self.estimate_tokens(text)
        
        # 内容类型分析
        chinese_ratio = len(re.findall(r'[\u4e00-\u9fff]', text)) / max(1, char_count)
        english_ratio = len(re.findall(r'[a-zA-Z]', text)) / max(1, char_count)
        code_ratio = len(re.findall(r'[{}[\]<>|\\`~]', text)) / max(1, char_count)
        
        # 效率分析
        tokens_per_char = exact_tokens / max(1, char_count)
        efficiency_score = min(1.0, char_count / max(1, exact_tokens))  # 理想为1.0
        
        return {
            "total_tokens": exact_tokens,
            "char_count": char_count,
            "tokens_per_char": tokens_per_char,
            "efficiency_score": efficiency_score,
            "content_ratios": {
                "chinese": chinese_ratio,
                "english": english_ratio,
                "code": code_ratio
            },
            "calculation_method": "tiktoken" if self._encoding_cache else "estimation",
            "encoding": self.encoding_name
        }
    
    def optimize_for_tokens(self, text: str, max_tokens: int, 
                          preserve_essential: bool = True) -> Tuple[str, Dict[str, Any]]:
        """优化文本以适应token限制"""
        if self.calculate_tokens(text) <= max_tokens:
            return text, {"optimized": False, "original_tokens": self.calculate_tokens(text)}
        
        original_tokens = self.calculate_tokens(text)
        optimization_steps = []
        
        # 步骤1：移除多余空白
        optimized_text = re.sub(r'\s+', ' ', text.strip())
        optimization_steps.append("whitespace_normalization")
        
        # 步骤2：智能截断（保留关键信息）
        if self.calculate_tokens(optimized_text) > max_tokens:
            if preserve_essential:
                optimized_text = self._intelligent_truncate(optimized_text, max_tokens)
                optimization_steps.append("intelligent_truncation")
            else:
                optimized_text = self._simple_truncate(optimized_text, max_tokens)
                optimization_steps.append("simple_truncation")
        
        # 步骤3：压缩标识符
        if self.calculate_tokens(optimized_text) > max_tokens:
            optimized_text = self._compress_identifiers(optimized_text)
            optimization_steps.append("identifier_compression")
        
        # 最终验证
        final_tokens = self.calculate_tokens(optimized_text)
        
        return optimized_text, {
            "optimized": True,
            "original_tokens": original_tokens,
            "final_tokens": final_tokens,
            "tokens_saved": original_tokens - final_tokens,
            "compression_ratio": 1 - (final_tokens / original_tokens),
            "optimization_steps": optimization_steps,
            "within_limit": final_tokens <= max_tokens
        }
    
    def _intelligent_truncate(self, text: str, max_tokens: int) -> str:
        """智能截断（保留关键信息）"""
        try:
            encoding = self.get_encoding()
            tokens = encoding.encode(text)
            
            if len(tokens) <= max_tokens:
                return text
            
            # 保留开头70%和结尾20%
            keep_tokens = int(max_tokens * 0.7)
            end_tokens = int(max_tokens * 0.2)
            
            if keep_tokens + end_tokens >= len(tokens):
                keep_tokens = max_tokens
            
            kept_tokens = tokens[:keep_tokens]
            
            if len(tokens) > keep_tokens + end_tokens:
                end_part_tokens = tokens[-end_tokens:]
                middle = encoding.decode([64004]) + "[内容已优化]" + encoding.decode([64004])  # 特殊标记
                return encoding.decode(kept_tokens) + middle + encoding.decode(end_part_tokens)
            else:
                return encoding.decode(tokens[:keep_tokens]) + "[截断]"
                
        except Exception:
            # 降级到字符截断
            return self._simple_truncate(text, max_tokens)
    
    def _simple_truncate(self, text: str, max_tokens: int) -> str:
        """简单截断"""
        estimated_chars = int(max_tokens * 1.5)  # 粗略估算
        if len(text) <= estimated_chars:
            return text
        
        return text[:estimated_chars] + "...[截断]"
    
    def _compress_identifiers(self, text: str) -> str:
        """压缩标识符"""
        # 替换长变量名为短形式
        compressed = text
        
        # 压缩常见模式
        patterns = [
            (r'\b([a-zA-Z_][a-zA-Z0-9_]{8,})\b', r'\1_short'),  # 长变量名
            (r'function\s+([a-zA-Z_][a-zA-Z0-9_]{8,})', r'func_\1'),  # 长函数名
            (r'class\s+([a-zA-Z_][a-zA-Z0-9_]{8,})', r'cls_\1'),    # 长类名
        ]
        
        for pattern, replacement in patterns:
            compressed = re.sub(pattern, replacement, compressed)
        
        return compressed
    
    def analyze_content_complexity(self, text: str) -> Dict[str, Any]:
        """分析内容复杂度"""
        if not text:
            return {"complexity_score": 0.0, "factors": {}}
        
        factors = {}
        
        # 词汇多样性
        words = re.findall(r'\b\w+\b', text.lower())
        unique_words = set(words)
        vocabulary_diversity = len(unique_words) / max(1, len(words))
        factors["vocabulary_diversity"] = vocabulary_diversity
        
        # 句子长度分布
        sentences = re.split(r'[.!?。！？]', text)
        avg_sentence_length = sum(len(s.strip()) for s in sentences) / max(1, len(sentences))
        factors["avg_sentence_length"] = avg_sentence_length
        
        # 嵌套深度（基于括号）
        max_nesting = max(
            (text.count('(') - text.count(')')),
            (text.count('[') - text.count(']')),
            (text.count('{') - text.count('}'))
        )
        factors["max_nesting_depth"] = max(0, max_nesting)
        
        # 代码密度
        code_indicators = len(re.findall(r'[{}[\]<>|\\`~]', text))
        factors["code_density"] = code_indicators / max(1, len(text))
        
        # 综合复杂度评分
        complexity_score = (
            vocabulary_diversity * 0.3 +
            min(1.0, avg_sentence_length / 50) * 0.3 +
            min(1.0, max_nesting / 10) * 0.2 +
            min(1.0, code_density * 100) * 0.2
        )
        
        return {
            "complexity_score": complexity_score,
            "factors": factors,
            "level": self._get_complexity_level(complexity_score)
        }
    
    def _get_complexity_level(self, score: float) -> str:
        """获取复杂度等级"""
        if score < 0.3:
            return "简单"
        elif score < 0.5:
            return "中等"
        elif score < 0.7:
            return "复杂"
        else:
            return "极复杂"
    
    def get_encoding_info(self) -> Dict[str, Any]:
        """获取编码器信息"""
        try:
            encoding = self.get_encoding()
            return {
                "name": self.encoding_name,
                "available": True,
                "type": type(encoding).__name__,
                "cache_status": "loaded" if self._encoding_cache else "not_loaded"
            }
        except Exception as e:
            return {
                "name": self.encoding_name,
                "available": False,
                "error": str(e),
                "fallback": "estimation"
            }


# 全局计算器实例
_token_calculators: Dict[str, TokenCalculator] = {}

def get_token_calculator(encoding_name: str = "cl100k_base") -> TokenCalculator:
    """获取token计算器（带缓存）"""
    if encoding_name not in _token_calculators:
        _token_calculators[encoding_name] = TokenCalculator(encoding_name)
    return _token_calculators[encoding_name]

def quick_estimate(text: str) -> int:
    """快速估算token数"""
    calculator = get_token_calculator()
    return calculator.estimate_tokens(text)

def precise_calculate(text: str, encoding: str = "cl100k_base") -> int:
    """精确计算token数"""
    calculator = get_token_calculator(encoding)
    return calculator.calculate_tokens(text)