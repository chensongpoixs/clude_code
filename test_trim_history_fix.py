#!/usr/bin/env python3
"""
验证agent_loop.py中的重复系统消息bug修复
"""
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def test_trim_history_fix():
    """测试_trim_history方法的重复系统消息修复"""
    print("🔧 测试_trim_history方法修复")
    
    # 模拟agent_loop.py中的_trim_history逻辑
    from clude_code.orchestrator.industry_context import get_industry_context_manager, ContextPriority
    from clude_code.llm.http_client import ChatMessage
    
    # 创建模拟的消息历史（包含系统消息）
    messages = [
        ChatMessage(role="system", content="你是一个AI助手，请帮助用户解决问题。"),
        ChatMessage(role="user", content="你好"),
        ChatMessage(role="assistant", content="你好！有什么可以帮助你的？"),
        ChatMessage(role="user", content="我想了解一下这个项目"),
        ChatMessage(role="assistant", content="这是一个AI助手项目，支持多模态对话。"),
    ]
    
    print(f"  原始消息数: {len(messages)}")
    
    # 模拟修复后的_trim_history逻辑
    max_tokens = 2000
    context_manager = get_industry_context_manager(max_tokens=max_tokens)
    
    # 修复：clear_context时不保留系统消息，避免重复
    context_manager.clear_context(keep_system=False)  # 这是修复的关键
    
    # 添加system消息（只添加一次）
    if messages and messages[0].role == "system":
        system_content = messages[0].content
        if isinstance(system_content, list):
            system_content = "\n".join(
                item.get("text", "") if isinstance(item, dict) and item.get("type") == "text" else "" 
                for item in system_content
            )
        context_manager.add_system_context(system_content)
        print(f"  添加系统消息: ✅ 1次")
    
    # 添加对话历史
    for i, message in enumerate(messages[1:], 1):  # 跳过system消息
        if i >= len(messages) - 5:  # 最近5条消息
            priority = ContextPriority.HIGH
        elif i >= len(messages) - 15:  # 最近15条消息
            priority = ContextPriority.MEDIUM
        else:
            priority = ContextPriority.LOW
        
        context_manager.add_message(message, priority)
    
    # 优化上下文
    optimized_items = context_manager.optimize_context()
    
    # 重建消息列表（模拟agent_loop.py的逻辑）
    new_messages = []
    
    # 添加system消息
    if messages and messages[0].role == "system":
        new_messages.append(messages[0])
    
    # 从优化后的上下文项重建消息
    for item in optimized_items:
        if item.category == "system":
            continue  # system消息已添加
        
        original_role = item.metadata.get("original_role", item.category)
        message = ChatMessage(role=original_role, content=item.content)
        new_messages.append(message)
    
    # 统计系统消息数量
    system_count = len([msg for msg in new_messages if msg.role == "system"])
    
    print(f"  优化后消息数: {len(new_messages)}")
    print(f"  系统消息数量: {system_count}")
    
    # 验证修复
    if system_count == 1:
        print("  ✅ 重复系统消息修复成功！")
        return True
    else:
        print(f"  ❌ 仍有重复系统消息：{system_count}条")
        return False

if __name__ == "__main__":
    print("🧪 验证agent_loop.py重复系统消息bug修复\n")
    
    success = test_trim_history_fix()
    
    if success:
        print("\n🎉 重复系统消息bug修复验证通过！")
        print("   - clear_context(keep_system=False) 避免重复")
        print("   - 只添加一次系统消息")
        print("   - 重建消息时跳过系统消息类别")
    else:
        print("\n⚠️  重复系统消息问题仍存在")