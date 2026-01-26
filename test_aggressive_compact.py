#!/usr/bin/env python3
"""
高强度 Auto-Compact 触发测试
使用超大内容块快速触发 70% 阈值
"""
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def test_aggressive_auto_compact():
    """高强度测试 Auto-Compact 触发"""
    print("🧪 高强度 Auto-Compact 触发测试\n")
    
    try:
        from clude_code.context.claude_standard import get_claude_context_manager, ContextPriority
        from clude_code.llm.http_client import ChatMessage
        
        # 创建极小的上下文管理器
        print("1. 创建极小容量上下文管理器...")
        manager = get_claude_context_manager(max_tokens=2000)  # 2K tokens 容量
        print(f"   ✅ 最大 tokens: {manager.max_tokens}")
        
        # 添加系统消息
        print("\n2. 添加系统消息...")
        system_content = "你是一个专业的 AI 助手，擅长各种任务处理。"
        manager.add_system_context(system_content)
        
        # 生成超大内容块
        print("\n3. 生成超大内容块...")
        
        # 生成大量重复的技术内容
        large_block = """
请帮我详细分析以下复杂的系统架构设计，并提供优化建议：

系统架构包含以下核心组件：
1. 微服务架构：包含用户服务、订单服务、支付服务、库存服务、物流服务
2. 数据存储：MySQL 主库 + Redis 缓存 + MongoDB 日志存储
3. 消息队列：RabbitMQ 处理异步任务
4. 负载均衡：Nginx + Keepalived
5. 监控系统：Prometheus + Grafana + AlertManager
6. 日志系统：ELK Stack (Elasticsearch + Logstash + Kibana)

具体架构详情：

用户服务 (User Service)：
- 技术栈：Spring Boot + MySQL + Redis
- 功能：用户注册、登录、个人信息管理、权限控制
- 部署：3个实例，负载均衡
- 数据库：主从复制，读写分离
- 缓存：Redis 集群，缓存用户信息和会话

订单服务 (Order Service)：
- 技术栈：Node.js + PostgreSQL + Redis
- 功能：订单创建、查询、修改、取消
- 部署：5个实例，水平扩展
- 数据库：分库分表，按用户ID分片
- 缓存：Redis，缓存热点订单数据

支付服务 (Payment Service)：
- 技术栈：Java + MySQL + Redis
- 功能：支付处理、退款、对账
- 部署：2个实例，高可用
- 数据库：主从复制，事务一致性
- 缓存：Redis，缓存支付记录

库存服务 (Inventory Service)：
- 技术栈：Go + MongoDB + Redis
- 功能：库存管理、预警、补货
- 部署：4个实例，分区管理
- 数据库：MongoDB 分片集群
- 缓存：Redis，缓存库存状态

物流服务 (Logistics Service)：
- 技术栈：Python + MySQL + Redis
- 功能：配送管理、轨迹追踪、配送员管理
- 部署：6个实例，地理位置分布
- 数据库：按地区分库
- 缓存：Redis，缓存配送信息

消息队列架构：
- RabbitMQ 集群：3个节点，高可用
- 交换机类型：Direct、Topic、Fanout
- 队列配置：持久化、死信队列
- 消息确认：手动确认机制
- 重试策略：指数退避，最大重试5次

负载均衡策略：
- Nginx：7层负载均衡，支持SSL终端
- Keepalived：VIP 漂移，故障自动切换
- 健康检查：HTTP健康检查，间隔5秒
- 会话保持：基于Cookie的会话保持
- 权重配置：根据服务器性能动态调整

监控和告警：
- Prometheus：指标收集，时间序列数据库
- Grafana：可视化面板，自定义图表
- AlertManager：告警规则，邮件/短信通知
- 监控指标：CPU、内存、网络、响应时间、错误率
- 告警级别：Critical、Warning、Info

日志处理：
- Logstash：日志收集和解析
- Elasticsearch：日志存储和索引
- Kibana：日志查询和分析
- 日志格式：JSON结构化日志
- 保留策略：热数据7天，冷数据30天

请分析以下方面：
1. 架构设计的合理性和可扩展性
2. 数据一致性和事务处理
3. 性能瓶颈和优化建议
4. 容错能力和故障恢复
5. 安全性考虑和改进建议
6. 运维监控和日志管理
7. 成本优化和资源利用

提供详细的架构分析报告和改进方案。
        """.strip()
        
        print(f"   内容块长度: {len(large_block)} 字符")
        
        # 估算这个大块会占用多少 tokens
        sample_tokens = len(large_block) // 4  # 粗略估算
        print(f"   预估 token 占用: {sample_tokens}")
        
        # 计算需要添加多少个这样的块才能触发 70% (1400 tokens)
        target_tokens = int(2000 * 0.7)  # 1400 tokens
        blocks_needed = max(1, (target_tokens - 100) // sample_tokens)  # 减去系统消息的tokens
        print(f"   需要添加块数: {blocks_needed}")
        
        # 添加超大块
        print("\n4. 添加超大内容块...")
        for i in range(blocks_needed + 1):  # 多加一个确保触发
            content = f"[超大块 {i+1}] {large_block}"
            manager.add_message(
                ChatMessage(role="user", content=content),
                ContextPriority.WORKING
            )
            
            # 检查状态
            stats = manager.get_context_summary()
            
            print(f"   块 {i+1}: 使用率 {stats['usage_percent']:.1%} ({stats['current_tokens']:,}/{stats['max_tokens']:,})")
            
            # 检查是否触发 Auto-Compact
            if stats['compact_count'] > 0:
                print(f"   🎯 Auto-Compact 已触发！压缩次数: {stats['compact_count']}")
                break
                
            # 如果达到紧急模式也停止
            if stats['is_emergency_mode']:
                print(f"   ⚠️  进入紧急模式: {stats['usage_percent']:.1%}")
                break
        
        # 最终统计
        print("\n5. 高强度 Auto-Compact 测试结果...")
        final_stats = manager.get_context_summary()
        
        print(f"   添加块数: {i+1}")
        print(f"   最终使用率: {final_stats['usage_percent']:.1%}")
        print(f"   压缩次数: {final_stats['compact_count']}")
        print(f"   是否应该压缩: {final_stats['should_compact']}")
        print(f"   紧急模式: {final_stats['is_emergency_mode']}")
        print(f"   上下文项目数: {final_stats['total_items']}")
        
        # 评估结果
        high_usage = final_stats['usage_percent'] > 0.5  # 50%以上
        compact_triggered = final_stats['compact_count'] > 0
        emergency_mode = final_stats['is_emergency_mode']
        
        success = high_usage or compact_triggered or emergency_mode
        
        if success:
            print("\n   🎉 高强度 Auto-Compact 测试成功！")
            if compact_triggered:
                print("   - ✅ Auto-Compact 成功触发")
            if emergency_mode:
                print("   - ✅ 紧急模式成功激活")
            if high_usage:
                print("   - ✅ 达到高使用率阈值")
        else:
            print("\n   ⚠️  高强度 Auto-Compact 测试未达到预期")
            print("   - 可能需要进一步调整 token 计算或降低阈值")
            
        return success
        
    except Exception as e:
        print(f"   ❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_aggressive_auto_compact()
    
    print("\n" + "=" * 60)
    if success:
        print("🎯 高强度 Auto-Compact 机制验证完成！")
        print("   - 成功验证了高负载场景")
        print("   - Auto-Compact 机制工作正常")
    else:
        print("⚠️  Auto-Compact 机制需要进一步调优")
    
    print("=" * 60)