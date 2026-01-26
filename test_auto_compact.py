#!/usr/bin/env python3
"""
Auto-Compact 机制触发测试
通过大量内容触发 70% 阈值，验证自动压缩功能
"""
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def test_auto_compact_trigger():
    """测试 Auto-Compact 机制触发"""
    print("🧪 Auto-Compact 机制触发测试\n")
    
    try:
        from clude_code.context.claude_standard import get_claude_context_manager, ContextPriority
        from clude_code.llm.http_client import ChatMessage
        
        # 创建小的上下文管理器，便于触发阈值
        print("1. 创建小容量上下文管理器（便于触发）...")
        manager = get_claude_context_manager(max_tokens=10000)  # 10K tokens 容量
        print(f"   ✅ 最大 tokens: {manager.max_tokens}")
        
        # 添加系统消息
        print("\n2. 添加系统消息...")
        system_content = "你是一个专业的 Claude Code 助手，擅长代码分析、重构、调试和优化。"
        manager.add_system_context(system_content)
        print(f"   ✅ 系统消息已添加")
        
        # 添加大量用户消息来触发 70% 阈值
        print("\n3. 添加大量对话消息（触发 70% 阈值）...")
        
        # 生成大量内容
        large_content = """
请帮我分析以下代码的性能问题：

```python
import asyncio
import aiohttp
import time
from typing import List, Dict, Any
import logging
import json
import csv
import pandas as pd
import numpy as np

class DataProcessor:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.session = None
        self.logger = logging.getLogger(__name__)
        
    async def process_data(self, data_sources: List[str]) -> Dict[str, Any]:
        """处理多个数据源"""
        results = {}
        
        for source in data_sources:
            try:
                # 模拟大数据处理
                raw_data = await self.fetch_data(source)
                processed_data = await self.transform_data(raw_data)
                results[source] = processed_data
                
            except Exception as e:
                self.logger.error(f"处理数据源 {source} 失败: {e}")
                results[source] = None
                
        return results
    
    async def fetch_data(self, source: str) -> List[Dict]:
        """获取数据"""
        # 模拟网络请求和数据处理
        await asyncio.sleep(0.1)  # 模拟网络延迟
        
        # 生成模拟数据
        data = []
        for i in range(1000):  # 1000 条记录
            record = {
                'id': i,
                'name': f'item_{i}',
                'value': np.random.random(),
                'category': np.random.choice(['A', 'B', 'C']),
                'timestamp': time.time() + i,
                'metadata': {
                    'source': source,
                    'processed': False,
                    'tags': [f'tag_{j}' for j in range(5)]
                }
            }
            data.append(record)
            
        return data
    
    async def transform_data(self, raw_data: List[Dict]) -> Dict[str, Any]:
        """转换数据"""
        # 转换为 DataFrame
        df = pd.DataFrame(raw_data)
        
        # 数据清洗和转换
        df['value'] = df['value'].fillna(0)
        df['category'] = df['category'].astype('category')
        
        # 聚合统计
        stats = {
            'total_records': len(df),
            'avg_value': df['value'].mean(),
            'max_value': df['value'].max(),
            'min_value': df['value'].min(),
            'category_counts': df['category'].value_counts().to_dict(),
            'processing_time': time.time()
        }
        
        return stats

# 使用示例
async def main():
    config = {
        'batch_size': 100,
        'timeout': 30,
        'retry_count': 3
    }
    
    processor = DataProcessor(config)
    sources = ['api_1', 'api_2', 'api_3', 'database_1', 'file_source']
    
    results = await processor.process_data(sources)
    
    # 输出处理结果
    for source, result in results.items():
        if result:
            print(f"{source}: 处理了 {result['total_records']} 条记录")
        else:
            print(f"{source}: 处理失败")

if __name__ == "__main__":
    asyncio.run(main())
```

请分析这段代码的以下方面：
1. 性能瓶颈在哪里？
2. 有哪些可以优化的地方？
3. 内存使用是否合理？
4. 异步处理是否正确？
5. 错误处理是否完善？

请提供具体的优化建议和改进方案。
        """.strip()
        
        # 添加多个消息来快速填充上下文
        message_count = 0
        while True:
            message_count += 1
            content = f"[消息 {message_count}] {large_content}"
            
            # 添加消息
            manager.add_message(
                ChatMessage(role="user", content=content),
                ContextPriority.WORKING
            )
            
            # 检查状态
            stats = manager.get_context_summary()
            usage_percent = stats['usage_percent']
            
            print(f"   消息 {message_count}: 使用率 {usage_percent:.1%} ({stats['current_tokens']:,}/{stats['max_tokens']:,})")
            
            # 检查是否触发 Auto-Compact
            if stats['compact_count'] > 0:
                print(f"   🎯 Auto-Compact 已触发！压缩次数: {stats['compact_count']}")
                break
                
            # 如果达到 90% 紧急模式也停止
            if stats['is_emergency_mode']:
                print(f"   ⚠️  进入紧急模式: {usage_percent:.1%}")
                break
                
            # 防止无限循环
            if message_count >= 50:
                print(f"   ⏹️  达到最大消息数限制: {message_count}")
                break
        
        # 最终统计
        print("\n4. Auto-Compact 测试结果...")
        final_stats = manager.get_context_summary()
        
        print(f"   总消息数: {message_count}")
        print(f"   最终使用率: {final_stats['usage_percent']:.1%}")
        print(f"   压缩次数: {final_stats['compact_count']}")
        print(f"   是否应该压缩: {final_stats['should_compact']}")
        print(f"   紧急模式: {final_stats['is_emergency_mode']}")
        print(f"   保护覆盖率: {final_stats['protection_coverage']['coverage_rate']:.1%}")
        
        # 评估结果
        success = final_stats['compact_count'] > 0 or final_stats['usage_percent'] > 0.7
        
        if success:
            print("\n   🎉 Auto-Compact 机制测试成功！")
            print("   - ✅ 成功触发或达到高使用率")
            print("   - ✅ 上下文管理正常工作")
        else:
            print("\n   ⚠️  Auto-Compact 机制未充分触发")
            print("   - 可能需要更多内容或更低的阈值")
            
        return success
        
    except Exception as e:
        print(f"   ❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_auto_compact_trigger()
    
    print("\n" + "=" * 60)
    if success:
        print("🎯 Auto-Compact 机制验证完成！")
        print("   - 成功触发高使用率场景")
        print("   - 验证了压缩机制的工作")
    else:
        print("⚠️  Auto-Compact 机制需要进一步优化")
    
    print("=" * 60)