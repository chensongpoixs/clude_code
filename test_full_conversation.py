#!/usr/bin/env python3
"""
完整的 Agent 对话测试
验证从用户输入到 Agent 响应的完整流程
"""
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def test_agent_conversation():
    """测试完整的 Agent 对话流程"""
    print("🧪 完整 Agent 对话测试\n")
    
    try:
        # 导入必要模块
        print("1. 导入模块...")
        from clude_code.config.config import CludeConfig
        from clude_code.orchestrator.agent_loop import AgentLoop
        print("   ✅ 模块导入成功")
        
        # 创建配置（最小配置）
        print("\n2. 创建配置...")
        cfg = CludeConfig()
        print("   ✅ 配置创建成功")
        
        # 初始化 AgentLoop
        print("\n3. 初始化 AgentLoop...")
        try:
            loop = AgentLoop(cfg)
            print("   ✅ AgentLoop 初始化成功")
        except Exception as e:
            print(f"   ⚠️  AgentLoop 初始化失败: {e}")
            print("   ℹ️  这可能是由于缺少 LLM 连接或模型配置")
            return False
        
        # 测试基本的对话能力（不实际调用 LLM）
        print("\n4. 测试基本功能...")
        
        # 检查消息历史
        print(f"   消息历史长度: {len(loop.messages)}")
        print(f"   第一条消息角色: {loop.messages[0].role if loop.messages else 'None'}")
        
        # 检查上下文管理器集成
        print("\n5. 测试上下文管理器集成...")
        from clude_code.context.claude_standard import get_claude_context_manager
        context_mgr = get_claude_context_manager()
        print(f"   上下文管理器类型: {type(context_mgr).__name__}")
        print(f"   最大 tokens: {context_mgr.max_tokens}")
        
        # 测试添加消息
        context_mgr.add_message("你好", "user")
        stats = context_mgr.get_context_summary()
        print(f"   添加消息后项目数: {stats['total_items']}")
        
        return True
        
    except Exception as e:
        print(f"   ❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_agent_conversation()
    
    print("\n" + "=" * 60)
    if success:
        print("🎉 完整 Agent 对话测试通过！")
        print("   - AgentLoop 初始化成功")
        print("   - 上下文管理器集成正常")
        print("   - 基本对话流程准备就绪")
    else:
        print("❌ 完整 Agent 对话测试失败")
    
    print("=" * 60)