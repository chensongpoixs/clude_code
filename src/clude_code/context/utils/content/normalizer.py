"""
内容标准化工具

处理多模态内容、格式转换和内容优化
"""
from typing import Union, List, Dict, Any, Optional, Tuple
import re
import json


class ContentNormalizer:
    """内容标准化器
    
    功能：
    - 多模态内容处理
    - 格式标准化
    - 内容优化
    - 编码转换
    """
    
    def __init__(self):
        self._content_cache: Dict[str, Any] = {}
    
    def normalize_content(self, content: Union[str, List, Dict], 
                        preserve_structure: bool = True) -> str:
        """标准化内容为字符串"""
        if isinstance(content, str):
            return content
        elif isinstance(content, list):
            return self._normalize_multimodal_list(content, preserve_structure)
        elif isinstance(content, dict):
            return self._normalize_structured_content(content, preserve_structure)
        else:
            return str(content)
    
    def _normalize_multimodal_list(self, content_list: List, 
                                 preserve_structure: bool = True) -> str:
        """标准化多模态列表内容"""
        text_parts = []
        image_refs = []
        audio_refs = []
        
        for i, item in enumerate(content_list):
            if isinstance(item, dict):
                item_type = item.get("type", "")
                
                if item_type == "text":
                    text = item.get("text", "")
                    if preserve_structure:
                        text_parts.append(f"[文本{i}] {text}")
                    else:
                        text_parts.append(text)
                
                elif item_type == "image_url":
                    url = item.get("image_url", {}).get("url", "")
                    image_refs.append(f"[图片{i}] {url}")
                
                elif item_type == "audio":
                    url = item.get("audio", {}).get("url", "")
                    audio_refs.append(f"[音频{i}] {url}")
                
                else:
                    # 其他类型转为文本描述
                    text_parts.append(f"[{item_type}] {str(item)}")
            
            elif isinstance(item, str):
                if preserve_structure:
                    text_parts.append(f"[内容{i}] {item}")
                else:
                    text_parts.append(item)
            else:
                text_parts.append(str(item))
        
        # 组合结果
        result = "\n".join(text_parts)
        
        if preserve_structure and (image_refs or audio_refs):
            # 添加媒体引用
            if image_refs:
                result += f"\n\n图片引用:\n" + "\n".join(image_refs)
            if audio_refs:
                result += f"\n\n音频引用:\n" + "\n".join(audio_refs)
        
        return result
    
    def _normalize_structured_content(self, content: Dict, 
                                  preserve_structure: bool = True) -> str:
        """标准化结构化内容"""
        if preserve_structure:
            try:
                # 尝试JSON格式化
                return json.dumps(content, ensure_ascii=False, indent=2)
            except (TypeError, ValueError):
                # 降级到字符串表示
                return str(content)
        else:
            # 提取文本内容
            text_parts = []
            
            def extract_text(obj, depth=0):
                if depth > 5:  # 防止过深递归
                    return
                
                if isinstance(obj, str):
                    text_parts.append(obj)
                elif isinstance(obj, dict):
                    for key, value in obj.items():
                        text_parts.append(f"[{key}]")
                        extract_text(value, depth + 1)
                elif isinstance(obj, list):
                    for i, item in enumerate(obj):
                        text_parts.append(f"[项目{i}]")
                        extract_text(item, depth + 1)
                else:
                    text_parts.append(str(obj))
            
            extract_text(content)
            return " ".join(text_parts)
    
    def extract_text_from_content(self, content: Union[str, List, Dict]) -> str:
        """提取纯文本内容"""
        if isinstance(content, str):
            return content
        
        # 从多模态内容提取文本
        if isinstance(content, list):
            text_parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_parts.append(item.get("text", ""))
                elif isinstance(item, str):
                    text_parts.append(item)
            return " ".join(text_parts)
        
        if isinstance(content, dict):
            # 递归提取文本
            def extract_strings(obj):
                strings = []
                if isinstance(obj, str):
                    strings.append(obj)
                elif isinstance(obj, dict):
                    for value in obj.values():
                        strings.extend(extract_strings(value))
                elif isinstance(obj, list):
                    for item in obj:
                        strings.extend(extract_strings(item))
                return strings
            
            return " ".join(extract_strings(content))
        
        return str(content)
    
    def optimize_text_for_llm(self, text: str, 
                              max_length: Optional[int] = None) -> Tuple[str, Dict[str, Any]]:
        """为LLM优化文本"""
        if not text:
            return text, {"optimized": False}
        
        original_length = len(text)
        optimized_text = text
        optimization_steps = []
        
        # 步骤1：标准化空白字符
        optimized_text = re.sub(r'\s+', ' ', optimized_text.strip())
        optimization_steps.append("whitespace_normalization")
        
        # 步骤2：移除特殊字符（如果可能）
        cleaned_text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', optimized_text)
        if len(cleaned_text) != len(optimized_text):
            optimized_text = cleaned_text
            optimization_steps.append("special_char_removal")
        
        # 步骤3：智能换行处理
        optimized_text = self._optimize_line_breaks(optimized_text)
        optimization_steps.append("line_break_optimization")
        
        # 步骤4：长度限制（如果指定）
        if max_length and len(optimized_text) > max_length:
            optimized_text = self._intelligent_truncate(optimized_text, max_length)
            optimization_steps.append("intelligent_truncation")
        
        # 统计优化结果
        final_length = len(optimized_text)
        reduction = original_length - final_length
        reduction_ratio = reduction / max(1, original_length)
        
        return optimized_text, {
            "optimized": final_length != original_length,
            "original_length": original_length,
            "final_length": final_length,
            "reduction": reduction,
            "reduction_ratio": reduction_ratio,
            "optimization_steps": optimization_steps
        }
    
    def _optimize_line_breaks(self, text: str) -> str:
        """优化换行符"""
        # 标准化换行符
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        
        # 移除过多的连续换行
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        # 移除行首行尾空白
        lines = text.split('\n')
        lines = [line.strip() for line in lines]
        
        # 过滤空行（保留最多一个连续空行）
        optimized_lines = []
        empty_count = 0
        
        for line in lines:
            if line:
                optimized_lines.append(line)
                empty_count = 0
            else:
                empty_count += 1
                if empty_count <= 1:
                    optimized_lines.append('')
        
        return '\n'.join(optimized_lines)
    
    def _intelligent_truncate(self, text: str, max_length: int) -> str:
        """智能截断文本"""
        if len(text) <= max_length:
            return text
        
        # 尝试在句子边界截断
        sentence_endings = ['.', '!', '?', '。', '！', '？']
        
        for i in range(max_length - 10, max_length + 1):
            if i < len(text) and text[i] in sentence_endings:
                return text[:i + 1] + " [截断]"
        
        # 尝试在单词边界截断
        for i in range(max_length, max(0, max_length - 50), -1):
            if i < len(text) and text[i].isspace():
                return text[:i].strip() + " [截断]"
        
        # 最后的字符截断
        return text[:max_length] + " [截断]"
    
    def analyze_content_structure(self, content: Union[str, List, Dict]) -> Dict[str, Any]:
        """分析内容结构"""
        analysis = {
            "content_type": "unknown",
            "has_multimedia": False,
            "structure_complexity": "simple",
            "text_extraction_possible": False,
            "component_count": 0,
            "components": {}
        }
        
        if isinstance(content, str):
            analysis.update({
                "content_type": "plain_text",
                "text_extraction_possible": True,
                "component_count": 1,
                "components": {"text": len(content)}
            })
        
        elif isinstance(content, list):
            components = {}
            multimedia_count = 0
            
            for i, item in enumerate(content):
                if isinstance(item, dict):
                    item_type = item.get("type", "unknown")
                    components[item_type] = components.get(item_type, 0) + 1
                    
                    if item_type in ["image_url", "audio", "video"]:
                        multimedia_count += 1
                
                elif isinstance(item, str):
                    components["text"] = components.get("text", 0) + len(item)
                else:
                    components["other"] = components.get("other", 0) + 1
            
            analysis.update({
                "content_type": "multimodal_list",
                "has_multimedia": multimedia_count > 0,
                "structure_complexity": "complex" if multimedia_count > 1 else "medium",
                "text_extraction_possible": True,
                "component_count": len(content),
                "components": components
            })
        
        elif isinstance(content, dict):
            components = {}
            
            def count_dict_items(obj, depth=0):
                if depth > 10:
                    return
                
                for key, value in obj.items():
                    key_type = type(value).__name__
                    components[key_type] = components.get(key_type, 0) + 1
                    
                    if isinstance(value, (dict, list)):
                        count_dict_items(value, depth + 1)
            
            count_dict_items(content)
            
            analysis.update({
                "content_type": "structured",
                "structure_complexity": "complex" if len(components) > 3 else "medium",
                "text_extraction_possible": True,
                "component_count": sum(components.values()),
                "components": components
            })
        
        return analysis
    
    def convert_to_standard_format(self, content: Union[str, List, Dict],
                                target_format: str = "string") -> Union[str, List, Dict]:
        """转换到标准格式"""
        if target_format == "string":
            return self.normalize_content(content, preserve_structure=False)
        
        elif target_format == "multimodal_list":
            if isinstance(content, list):
                return content
            elif isinstance(content, str):
                return [{"type": "text", "text": content}]
            else:
                return [{"type": "text", "text": str(content)}]
        
        elif target_format == "structured":
            if isinstance(content, dict):
                return content
            else:
                return {"text": self.normalize_content(content, preserve_structure=False)}
        
        else:
            raise ValueError(f"Unsupported target format: {target_format}")
    
    def detect_content_encoding_issues(self, text: str) -> Dict[str, Any]:
        """检测内容编码问题"""
        issues = []
        fixes = []
        
        # 检测常见编码问题
        if '\uFFFD' in text:  # 替换字符
            issues.append("contains_replacement_chars")
            fixes.append("unicode_normalization")
        
        if len(text) != len(text.encode('utf-8', errors='ignore')):
            issues.append("encoding_mismatch")
            fixes.append("utf8_encoding_fix")
        
        # 检测控制字符
        control_chars = len(re.findall(r'[\x00-\x1F\x7F]', text))
        if control_chars > 0:
            issues.append("contains_control_chars")
            fixes.append("control_char_removal")
        
        # 检测BOM
        if text.startswith('\ufeff'):
            issues.append("contains_bom")
            fixes.append("bom_removal")
        
        return {
            "has_issues": len(issues) > 0,
            "issues": issues,
            "suggested_fixes": fixes,
            "control_char_count": control_chars,
            "text_length": len(text),
            "encoding_safe": len(issues) == 0
        }


# 全局标准化器实例
_default_normalizer: Optional[ContentNormalizer] = None

def get_content_normalizer() -> ContentNormalizer:
    """获取默认内容标准化器"""
    global _default_normalizer
    if _default_normalizer is None:
        _default_normalizer = ContentNormalizer()
    return _default_normalizer

def normalize_for_llm(content: Union[str, List, Dict], 
                    preserve_structure: bool = True) -> str:
    """为LLM标准化内容"""
    normalizer = get_content_normalizer()
    return normalizer.normalize_content(content, preserve_structure)

def extract_text_safely(content: Union[str, List, Dict]) -> str:
    """安全提取文本内容"""
    normalizer = get_content_normalizer()
    return normalizer.extract_text_from_content(content)