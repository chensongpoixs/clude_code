#!/usr/bin/env python3
"""
调试 AgentLoop 执行阶段问题的脚本
模拟"列出当前目录的前3个文件"这个多步骤任务
"""

import json
import sys
import os

# Add src to path to import clude_code modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from clude_code.orchestrator.agent_loop.control_protocol import try_parse_control_envelope
from clude_code.orchestrator.agent_loop.parsing import try_parse_tool_call

def test_control_protocol_parsing():
    """测试控制协议解析"""
    print("=== 测试控制协议解析 ===")
    
    # Test cases
    test_cases = [
        '{"control":"step_done"}',
        '{"control": "step_done"}',
        '{"control":"step_done","reason":"task completed"}',
        'Some text before {"control":"step_done"} and after',
        '```json\n{"control":"step_done"}\n```',
        'STEP_DONE',  # Old protocol
        '【STEP_DONE】',
        'Some random text',
        '',
        '{"invalid": "json"}',
        '{"control": "invalid_control"}',
        'I have completed the task successfully.',
    ]
    
    for i, test_input in enumerate(test_cases, 1):
        print(f"\n测试用例 {i}: {repr(test_input)}")
        ctrl = try_parse_control_envelope(test_input)
        if ctrl:
            print(f"  ✓ 解析成功: control={ctrl.control}, reason={ctrl.reason}")
        else:
            print("  ✗ 解析失败，回退到其他处理")
            
            # Test tool call parsing as fallback
            tool_call = try_parse_tool_call(test_input)
            if tool_call:
                print(f"  → 解析为工具调用: {tool_call}")
            else:
                print("  → 不是工具调用也不是控制信号")

def test_step_execution_flow():
    """模拟步骤执行流程"""
    print("\n=== 模拟步骤执行流程 ===")
    
    # Simulate LLM responses for different iterations
    llm_responses = [
        # First iteration - tool call
        '{"tool": "list_dir", "args": {"path": ".", "max_items": 3}}',
        
        # Second iteration - should be step_done but might be problematic
        'I have listed the directory contents successfully.',
        
        # Third iteration - another tool call (this would be the problem)
        '{"tool": "list_dir", "args": {"path": ".", "max_items": 3}}',
        
        # Correct step_done response
        '{"control":"step_done"}',
    ]
    
    print("模拟多轮步骤执行:")
    for i, response in enumerate(llm_responses, 1):
        print(f"\n--- 轮次 {i} ---")
        print(f"LLM响应: {response}")
        
        # First, try to parse as control signal
        ctrl = try_parse_control_envelope(response)
        if ctrl:
            print(f"→ 控制信号: {ctrl.control}")
            if ctrl.control == "step_done":
                print("✓ 步骤完成，应该进入下一步")
                break
            elif ctrl.control == "replan":
                print("⚠ 需要重规划")
                break
            continue
        
        # Then try to parse as tool call
        tool_call = try_parse_tool_call(response)
        if tool_call:
            print(f"→ 工具调用: {tool_call['tool']}")
            print("  执行工具，结果将回喂给LLM")
            continue
        
        # Neither control nor tool call
        print("→ 无效输出，既不是控制信号也不是工具调用")
        print("  应该返回错误提示让LLM重试")

def analyze_loop_condition():
    """分析可能导致无限循环的条件"""
    print("\n=== 分析无限循环条件 ===")
    
    problem_scenarios = [
        {
            "name": "LLM不输出控制信号",
            "description": "LLM完成工具调用后，不输出{\"control\":\"step_done\"}，而是输出其他文本",
            "result": "系统无法识别步骤完成，继续下一轮工具调用"
        },
        {
            "name": "工具调用解析失败",
            "description": "LLM输出的工具调用JSON格式不正确",
            "result": "系统无法识别为工具调用，也不能识别为控制信号"
        },
        {
            "name": "控制信号格式错误",
            "description": "LLM输出类似{control: step_done}（缺少引号）或其他错误格式",
            "result": "控制协议解析失败，回退到字符串匹配也可能失败"
        },
        {
            "name": "错误重试机制失效",
            "description": "系统返回错误提示，但LLM依然不按规则输出",
            "result": "无限重试循环"
        }
    ]
    
    for scenario in problem_scenarios:
        print(f"\n问题场景: {scenario['name']}")
        print(f"描述: {scenario['description']}")
        print(f"结果: {scenario['result']}")

if __name__ == "__main__":
    print("AgentLoop 执行阶段问题调试脚本")
    print("=" * 50)
    
    test_control_protocol_parsing()
    test_step_execution_flow()
    analyze_loop_condition()
    
    print("\n" + "=" * 50)
    print("调试完成")
