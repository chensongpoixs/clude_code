#!/usr/bin/env python3
"""
PlanPatch JSON解析问题修复方案
解决"Field required"错误和JSON解析失败问题
"""

import json
import re
from typing import Any, Dict, List, Optional, Tuple
from pydantic import ValidationError

def enhanced_extract_json_candidates(text: str) -> List[str]:
    """
    增强的JSON候选提取，支持更多格式
    """
    candidates = []
    
    # 1. 标准fenced code block
    fenced_patterns = [
        r'```json\s*\n(.*?)\n```',
        r'```\s*\n(.*?)\n```',
        r'```json\s*(.*?)```',
        r'```(.*?)```'
    ]
    
    for pattern in fenced_patterns:
        matches = re.findall(pattern, text, re.DOTALL | re.IGNORECASE)
        candidates.extend(matches)
    
    # 2. 花括号包裹的JSON（更宽松的匹配）
    brace_matches = re.findall(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, re.DOTALL)
    candidates.extend(brace_matches)
    
    # 3. 寻找可能的PlanPatch字段
    patch_fields = ['update_steps', 'add_steps', 'remove_steps', 'type']
    for field in patch_fields:
        pattern = rf'"{field}"\s*:\s*\[.*?\](?=\s*[,}}])'
        matches = re.findall(pattern, text, re.DOTALL)
        if matches:
            # 尝试构建完整的JSON对象
            for match in matches:
                json_str = f'{{"{field}": {match}}}'
                candidates.append(json_str)
    
    return candidates

def robust_parse_plan_patch(text: str) -> Tuple[Optional[Dict], str]:
    """
    健壮的PlanPatch解析，提供详细的错误信息
    """
    candidates = enhanced_extract_json_candidates(text)
    last_error = ""
    
    for i, candidate in enumerate(candidates):
        try:
            # 清理候选字符串
            candidate = candidate.strip()
            
            # 修复常见的JSON格式问题
            candidate = fix_common_json_issues(candidate)
            
            obj = json.loads(candidate)
            
            if not isinstance(obj, dict):
                last_error = f"候选 {i+1}: 不是有效的JSON对象"
                continue
            
            # 验证是否为PlanPatch格式
            if is_valid_plan_patch_format(obj):
                return obj, f"解析成功（候选 {i+1}）"
            else:
                last_error = f"候选 {i+1}: 不是有效的PlanPatch格式"
                
        except json.JSONDecodeError as e:
            last_error = f"候选 {i+1}: JSON解码错误 - {str(e)}"
            continue
        except Exception as e:
            last_error = f"候选 {i+1}: 未知错误 - {str(e)}"
            continue
    
    return None, last_error

def fix_common_json_issues(json_str: str) -> str:
    """
    修复常见的JSON格式问题
    """
    # 1. 修复单引号问题
    json_str = re.sub(r"'([^']*)'", r'"\1"', json_str)
    
    # 2. 修复尾随逗号
    json_str = re.sub(r',\s*([}\]])', r'\1', json_str)
    
    # 3. 修复未引用的键名
    json_str = re.sub(r'(\w+)\s*:', r'"\1":', json_str)
    
    # 4. 移除注释
    json_str = re.sub(r'//.*?\n', '\n', json_str)
    json_str = re.sub(r'/\*.*?\*/', '', json_str, flags=re.DOTALL)
    
    return json_str

def is_valid_plan_patch_format(obj: Dict) -> bool:
    """
    验证是否为有效的PlanPatch格式
    """
    # 必须有type字段且为PlanPatch
    if obj.get('type') != 'PlanPatch':
        return False
    
    # 至少有一个操作字段
    operations = ['update_steps', 'add_steps', 'remove_steps']
    has_operation = any(field in obj for field in operations)
    
    return has_operation

def enhanced_parse_plan_patch_with_fallback(text: str) -> Dict:
    """
    增强的PlanPatch解析，包含完整的错误处理和回退机制
    """
    # 首先尝试健壮解析
    obj, error_msg = robust_parse_plan_patch(text)
    
    if obj is not None:
        return obj
    
    # 如果失败，尝试构建最小可用的PlanPatch
    return create_minimal_plan_patch(text)

def create_minimal_plan_patch(text: str) -> Dict:
    """
    从文本中提取信息创建最小的PlanPatch
    """
    minimal_patch = {
        "type": "PlanPatch",
        "update_steps": [],
        "add_steps": [],
        "remove_steps": []
    }
    
    # 尝试从文本中提取步骤更新信息
    update_patterns = [
        r'更新步骤["\']?\s*["\']?(\w+)["\']?\s*[:：]\s*([^,\n]+)',
        r'modify\s+step\s*(\w+)[:：]\s*([^,\n]+)',
        r'change\s+(\w+)\s+to\s+([^,\n]+)'
    ]
    
    for pattern in update_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for step_id, description in matches:
            minimal_patch["update_steps"].append({
                "id": step_id.strip(),
                "description": description.strip()
            })
    
    # 尝试从文本中提取新增步骤信息
    add_patterns = [
        r'添加步骤["\']?\s*["\']?(\w+)["\']?\s*[:：]\s*([^,\n]+)',
        r'add\s+step\s*(\w+)[:：]\s*([^,\n]+)',
        r'新增\s+(\w+)\s*[:：]\s*([^,\n]+)'
    ]
    
    for pattern in add_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for step_id, description in matches:
            minimal_patch["add_steps"].append({
                "id": step_id.strip(),
                "description": description.strip(),
                "dependencies": []
            })
    
    return minimal_patch

print("PlanPatch解析修复方案已生成")
print("- 增强JSON候选提取")
print("- 修复常见格式问题") 
print("- 提供详细错误信息")
print("- 包含回退机制")
