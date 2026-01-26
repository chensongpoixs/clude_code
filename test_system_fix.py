#!/usr/bin/env python3
"""
测试重复系统消息修复验证
"""
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from clude_code.orchestrator.industry_context import get_industry_context_manager

def test_duplicate_system_fix():
    """测试重复系统消息修复"""
    print("🔧 测试重复系统消息修复")
    
    # 创建上下文管理器
    manager = get_industry_context_manager(max_tokens=2000)
    
    # 第一次添加系统消息
    system_msg1 = "你是一个AI助手。请帮助用户解决问题。"
    manager.add_system_context(system_msg1)
    
    # 添加对话消息
    manager.add_message("你好，我想问个问题", priority=3)
    manager.add_message("你好！请问有什么可以帮助你的？", priority=3)
    
    # 优化上下文
    optimized1 = manager.optimize_context()
    system_count1 = len([item for item in optimized1 if item.category in ["system", "system_compressed"]])
    
    print(f"  第一次优化后系统消息数: {system_count1}")
    print(f"  第一次优化后总消息数: {len(optimized1)}")
    
    # 模拟重复添加系统消息的场景（原bug）
    manager2 = get_industry_context_manager(max_tokens=2000)
    
    # 错误的重复添加方式（原bug会这样做）
    manager2.add_system_context(system_msg1)
    # 如果有bug，这里会重复添加
    manager2.add_system_context(system_msg1)  # 模拟重复
    
    # 添加相同对话消息
    manager2.add_message("你好，我想问个问题", priority=3)
    manager2.add_message("你好！请问有什么可以帮助你的？", priority=3)
    
    optimized2 = manager2.optimize_context()
    system_count2 = len([item for item in optimized2 if item.category in ["system", "system_compressed"]])
    
    print(f"  重复添加后系统消息数: {system_count2}")
    print(f"  重复添加后总消息数: {len(optimized2)}")
    
    # 验证修复
    if system_count2 == 1:
        print("  ✅ 重复系统消息修复成功！")
        return True
    else:
        print(f"  ❌ 仍有重复系统消息：{system_count2}条")
        return False

if __name__ == "__main__":
    print("🧪 验证重复系统消息修复\n")
    
    success = test_duplicate_system_fix()
    
    if success:
        print("\n🎉 重复系统消息bug修复验证通过！")
    else:
        print("\n⚠️  重复系统消息问题仍存在")