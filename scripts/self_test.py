#!/usr/bin/env python
"""自我修复性测试脚本"""

import os
import sys
import time
import json

# 切换到项目目录
os.chdir("D:/Work/AI/clude_code")
sys.path.insert(0, "src")

from clude_code.config.config import CludeConfig
from clude_code.llm.http_client import LlamaCppHttpClient, ChatMessage

def test_basic_chat():
    """测试1: 基本对话 - 你好啊"""
    print("=" * 60)
    print("测试 1: 基本对话 - 你好啊")
    print("=" * 60)
    
    cfg = CludeConfig()
    print(f"\n配置信息:")
    print(f"  Provider: {cfg.llm.provider}")
    print(f"  Model: {cfg.llm.model}")
    print(f"  Base URL: {cfg.llm.base_url}")
    
    # 创建 LLM 客户端
    client = LlamaCppHttpClient(
        base_url=cfg.llm.base_url,
        model=cfg.llm.model,
        api_key=cfg.llm.api_key,
        api_mode=cfg.llm.api_mode,
        temperature=cfg.llm.temperature,
        max_tokens=cfg.llm.max_tokens,
        timeout_s=cfg.llm.timeout_s,
    )
    
    # 发送测试消息
    messages = [
        ChatMessage(role="user", content="你好啊")
    ]
    
    print(f"\n发送消息: 你好啊")
    print("-" * 40)
    
    try:
        t0 = time.time()
        response = client.chat(messages)
        elapsed = time.time() - t0
        
        print(f"\n响应内容 ({elapsed:.2f}s):")
        print(response)
        print("-" * 40)
        
        return True, response
        
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        return False, str(e)


def test_tool_call():
    """测试2: 工具调用 - 获取北京的天气"""
    print("\n" + "=" * 60)
    print("测试 2: 工具调用 - 获取北京的天气")
    print("=" * 60)
    
    cfg = CludeConfig()
    
    # 创建 LLM 客户端
    client = LlamaCppHttpClient(
        base_url=cfg.llm.base_url,
        model=cfg.llm.model,
        api_key=cfg.llm.api_key,
        api_mode=cfg.llm.api_mode,
        temperature=cfg.llm.temperature,
        max_tokens=cfg.llm.max_tokens,
        timeout_s=cfg.llm.timeout_s,
    )
    
    # 系统提示词（包含工具说明）
    system_prompt = """你是一个智能助手，可以使用以下工具：

## 可用工具

### web_search
搜索网络获取信息
参数:
- query: 搜索关键词

当用户询问天气时，请使用 web_search 工具搜索天气信息。

请以 JSON 格式返回工具调用：
```json
{
  "tool": "web_search",
  "parameters": {"query": "北京天气"}
}
```
"""
    
    messages = [
        ChatMessage(role="system", content=system_prompt),
        ChatMessage(role="user", content="获取北京的天气")
    ]
    
    print(f"\n发送消息: 获取北京的天气")
    print("-" * 40)
    
    try:
        t0 = time.time()
        response = client.chat(messages)
        elapsed = time.time() - t0
        
        print(f"\n响应内容 ({elapsed:.2f}s):")
        print(response)
        print("-" * 40)
        
        # 检查是否返回了工具调用
        if "web_search" in response or "tool" in response:
            print("\n✅ 模型识别到需要使用工具")
        else:
            print("\n⚠️ 模型未返回工具调用")
        
        return True, response
        
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        return False, str(e)


def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("       自我修复性测试")
    print("=" * 60)
    print(f"测试时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    results = {}
    
    # 测试 1: 基本对话
    success1, resp1 = test_basic_chat()
    results["你好啊"] = {"success": success1, "response": resp1[:200] if resp1 else ""}
    
    # 测试 2: 工具调用
    success2, resp2 = test_tool_call()
    results["获取北京的天气"] = {"success": success2, "response": resp2[:200] if resp2 else ""}
    
    # 汇总结果
    print("\n" + "=" * 60)
    print("       测试结果汇总")
    print("=" * 60)
    
    for test_name, result in results.items():
        status = "✅ 通过" if result["success"] else "❌ 失败"
        print(f"  {test_name}: {status}")
    
    return results


if __name__ == "__main__":
    main()

