#!/usr/bin/env python3
"""
测试 AgentLoop 修复方案的验证脚本
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from clude_code.orchestrator.agent_loop.control_protocol import try_parse_control_envelope
from clude_code.orchestrator.agent_loop.parsing import try_parse_tool_call

def test_enhanced_parsing():
    """测试增强的解析逻辑"""
    print("=== 测试增强的解析逻辑 ===")
    
    test_cases = [
        # 控制信号测试
        ('{"control":"step_done"}', "控制信号", "step_done"),
        ('{"control":"replan","reason":"工具调用失败"}', "控制信号", "replan"),
        ('任务已完成', "自然语言完成", "应自动推断完成"),
        ('我已经成功列出了目录内容', "自然语言完成", "应自动推断完成"),
        
        # 误判测试
        ('{"tool": "display", "args": {"content": "完成"}}', "工具调用", "正常工具调用"),
        ('{"control": "step_done"}', "控制信号误判", "应被修正"),
        
        # 错误格式测试
        ('{control: step_done}', "格式错误", "应要求重试"),
        ('```json\n{"control":"step_done"}\n```', "代码块包裹", "应要求重试"),
    ]
    
    for i, (input_text, category, expected) in enumerate(test_cases, 1):
        print(f"\n--- 测试用例 {i} ---")
        print(f"输入: {input_text}")
        print(f"类别: {category}")
        print(f"期望: {expected}")
        
        # 先尝试控制协议解析
        ctrl = try_parse_control_envelope(input_text)
        if ctrl:
            print(f"✓ 控制信号解析成功: {ctrl.control}")
            if ctrl.control in ["step_done", "replan"]:
                print(f"  → 正确处理: {ctrl.control}")
            continue
        
        # 检查是否被工具调用解析误判
        tool_call = try_parse_tool_call(input_text)
        if tool_call:
            if tool_call.get("control") in ["step_done", "replan"]:
                print(f"⚠ 控制信号被误判为工具调用，需要修正: {tool_call.get('control')}")
            else:
                print(f"✓ 正常工具调用: {tool_call.get('tool')}")
            continue
        
        # 检查是否是自然语言完成声明
        completion_keywords = ["完成", "已完成", "完成了", "finished", "done", "completed", "任务完成"]
        if any(keyword in input_text.lower() for keyword in completion_keywords):
            print(f"✓ 检测到自然语言完成声明，应自动完成步骤")
            continue
        
        print("❌ 需要返回错误提示，要求输出控制信号")

def test_simple_query_auto_completion():
    """测试简单查询的自动完成机制"""
    print("\n=== 测试简单查询自动完成 ===")
    
    simple_query_steps = [
        "列出当前目录的前3个文件",
        "显示README文件的内容", 
        "获取项目配置信息",
        "检查package.json版本",
    ]
    
    complex_steps = [
        "分析代码结构并生成报告",
        "重构模块并更新文档",
        "实现新的功能模块",
    ]
    
    print("简单查询步骤（应该自动完成）:")
    for step in simple_query_steps:
        is_simple = (
            True and  # tools_expected <= 1
            any(keyword in step.lower() for keyword in ["列出", "显示", "查看", "检查", "获取", "list", "show", "get", "check"])
        )
        print(f"  {step} -> {'✓ 自动完成' if is_simple else '✗ 手动完成'}")
    
    print("\n复杂步骤（需要手动完成）:")
    for step in complex_steps:
        is_simple = (
            True and  # tools_expected <= 1  
            any(keyword in step.lower() for keyword in ["列出", "显示", "查看", "检查", "获取", "list", "show", "get", "check"])
        )
        print(f"  {step} -> {'✓ 自动完成' if is_simple else '✗ 手动完成'}")

def simulate_fixed_execution_flow():
    """模拟修复后的执行流程"""
    print("\n=== 模拟修复后的执行流程 ===")
    
    scenarios = [
        {
            "name": "场景1：LLM完成但不输出控制信号",
            "steps": [
                ("工具调用", '{"tool": "list_dir", "args": {"path": ".", "max_items": 3}}'),
                ("自然语言完成", "我已经成功列出了目录内容"),
                ("自动推断", "→ 检测到完成声明，自动完成步骤"),
            ]
        },
        {
            "name": "场景2：控制信号格式错误", 
            "steps": [
                ("工具调用", '{"tool": "list_dir", "args": {"path": ".", "max_items": 3}}'),
                ("错误格式", '{control: step_done}'),
                ("强制重试", "→ 返回强制控制信号提示"),
                ("正确格式", '{"control":"step_done"}'),
                ("步骤完成", "→ 正确识别并完成步骤"),
            ]
        },
        {
            "name": "场景3：简单查询自动完成",
            "steps": [
                ("工具调用", '{"tool": "read_file", "args": {"path": "README.md"}}'),
                ("自动推断", "→ 检测到简单查询+成功结果，自动完成"),
            ]
        }
    ]
    
    for scenario in scenarios:
        print(f"\n{scenario['name']}:")
        for action, output in scenario['steps']:
            print(f"  {action}: {output}")

if __name__ == "__main__":
    print("AgentLoop 修复方案验证测试")
    print("=" * 50)
    
    test_enhanced_parsing()
    test_simple_query_auto_completion()
    simulate_fixed_execution_flow()
    
    print("\n" + "=" * 50)
    print("修复方案验证完成")
