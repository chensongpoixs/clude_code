# P1-1: TaskAgent 异步执行问题修复

> **状态**: 🔄 进行中  
> **开始时间**: 2026-01-23

---

## 1. 问题分析

### 1.1 当前行为
```python
# task_agent.py L205
result = asyncio.run(manager.execute_task(task.task_id))  # ← 问题所在
```

### 1.2 问题
- `asyncio.run()` 会创建一个新的事件循环并运行直到完成
- 如果当前已经在一个事件循环中（Jupyter/IPython/GUI 框架），会抛出：
  `RuntimeError: This event loop is already running.`
- 违背了 asyncio 的"一个线程一个循环"原则

### 1.3 业界对标
| 系统 | 策略 |
| :--- | :--- |
| LangChain | 使用 `nest_asyncio` 补丁或完全同步 |
| LlamaIndex | 检测现有循环，使用 `run_coroutine_threadsafe` |
| FastAPI | 在异步上下文中保持异步，在同步入口点使用 uvloop |

---

## 2. 设计方案

### 2.1 技术路线
采用"同步降级 + 异步兼容"策略：

1. **同步降级**：当前的 agent handlers 只是模拟（sleep），实际上不需要异步。
   将它们改为同步函数，使用 `time.sleep` 而非 `asyncio.sleep`。

2. **保留异步接口**：`TaskManager.execute_task` 可保留为 async，但调用时使用安全包装。

3. **安全包装函数**：提供一个 `run_sync` 函数，能够处理"已有循环"和"无循环"两种情况。

### 2.2 安全 asyncio 调用封装
```python
def run_sync(coro):
    """安全地在同步上下文中执行协程。"""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # 没有运行中的循环，可以安全使用 asyncio.run
        return asyncio.run(coro)
    else:
        # 已有循环，使用线程池执行
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result()
```

### 2.3 简化方案（推荐）
由于当前 handlers 只是模拟，直接改为同步实现更简单：
- 移除 `async def` 和 `await`
- 使用 `time.sleep()` 替代 `asyncio.sleep()`
- 删除 `asyncio.run()` 调用

---

## 3. 实现步骤

- [x] 3.1 将 agent handlers 改为同步函数 ✅
- [x] 3.2 将 `TaskManager.execute_task` 改为同步方法 ✅
- [x] 3.3 移除 `asyncio.run()` 调用和 import ✅
- [x] 3.4 编译检查 ✅ 通过
- [x] 3.5 验证汇报 ✅ 完成

---

## 5. 验证结果

### 5.1 编译检查
```
python -m compileall -q task_agent.py
# Exit code: 0 ✅
```

### 5.2 核心变更摘要

| 变更 | Before | After |
| :--- | :--- | :--- |
| `execute_task` | `async def ... await handler()` | `def ... handler()` |
| handlers | `async def ... await asyncio.sleep()` | `def ... time.sleep()` |
| run_task 调用 | `asyncio.run(manager.execute_task(...))` | `manager.execute_task(...)` |
| import | `import asyncio` | 已移除 |

### 5.3 预期收益
- 消除"event loop already running"错误
- 在 Jupyter/IPython/GUI 环境中正常工作
- 代码更简单，无嵌套 asyncio 风险

---

## 4. 代码变更清单

| 文件 | 变更类型 | 说明 |
| :--- | :--- | :--- |
| `src/clude_code/tooling/tools/task_agent.py` | 修改 | 同步化 agent handlers 和 execute_task |


