# 动态模型切换功能设计

> **创建时间**：2026-01-23  
> **功能类型**：全局配置增强

---

## 1. 需求分析

### 1.1 功能目标

- **动态切换**：在运行时（不重启）切换 LLM 模型
- **全局生效**：切换后影响所有后续的 LLM 调用
- **多种入口**：支持 CLI 命令、对话斜杠命令、API 调用

### 1.2 使用场景

| 场景 | 描述 |
|------|------|
| 启动时选择 | `clude chat --select-model` 已支持 |
| 对话中切换 | `/model <name>` 切换到指定模型 |
| 查看当前 | `/model` 显示当前模型 |
| 列出可用 | `/models` 列出所有可用模型 |

### 1.3 业界对标

| 项目 | 模型切换方式 |
|------|-------------|
| OpenAI Playground | 下拉菜单实时切换 |
| Aider | `--model` 参数 + `/model` 命令 |
| LangChain | `model_name` 参数动态传递 |
| Cursor | 设置面板 + 快捷键 |

---

## 2. 架构设计

### 2.1 组件

```
┌─────────────────────────────────────────────────────────┐
│                    ModelManager (单例)                   │
│  - current_model: str                                   │
│  - available_models: list[str]                          │
│  - switch_model(name) -> bool                           │
│  - list_models() -> list[str]                           │
│  - refresh_models() -> None                             │
│  - on_model_changed: list[Callable]                     │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│              LlamaCppHttpClient                         │
│  + set_model(name) -> None  # 新增                      │
│  + get_model() -> str       # 新增                      │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│                    AgentLoop                            │
│  + switch_model(name) -> bool  # 新增                   │
│  + get_current_model() -> str  # 新增                   │
└─────────────────────────────────────────────────────────┘
```

### 2.2 数据流

```
用户输入 "/model gpt-4"
        │
        ▼
┌─────────────────┐
│ 斜杠命令解析器   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  ModelManager   │ ─── 验证模型是否可用
└────────┬────────┘
         │ switch_model()
         ▼
┌─────────────────┐
│  LLM Client     │ ─── 更新 self.model
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 触发 on_changed │ ─── 通知 UI/日志
└─────────────────┘
```

---

## 3. 实现计划

### 3.1 文件修改清单

| 文件 | 修改内容 |
|------|---------|
| `src/clude_code/llm/llama_cpp_http.py` | 添加 `set_model()` / `get_model()` / `list_models()` |
| `src/clude_code/llm/model_manager.py` | **新建** - 模型管理器单例 |
| `src/clude_code/orchestrator/agent_loop/agent_loop.py` | 添加 `switch_model()` |
| `src/clude_code/cli/slash_commands.py` | 添加 `/model` 和 `/models` 命令 |
| `src/clude_code/cli/chat_handler.py` | 集成斜杠命令处理 |

### 3.2 实现步骤

#### Step 1: LLM 客户端增强

```python
# llama_cpp_http.py

def set_model(self, model: str) -> None:
    """动态切换模型"""
    self.model = model

def get_model(self) -> str:
    """获取当前模型"""
    return self.model

def list_models(self) -> list[str]:
    """从 /v1/models 获取可用模型列表"""
    try:
        resp = httpx.get(f"{self.base_url}/v1/models", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            return [m["id"] for m in data.get("data", [])]
    except Exception:
        pass
    return []
```

#### Step 2: 模型管理器

```python
# model_manager.py

class ModelManager:
    """全局模型管理器（单例）"""
    
    _instance = None
    
    def __init__(self):
        self._llm_client: LlamaCppHttpClient | None = None
        self._on_changed: list[Callable] = []
    
    @classmethod
    def get_instance(cls) -> "ModelManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def bind(self, llm_client: LlamaCppHttpClient) -> None:
        """绑定 LLM 客户端"""
        self._llm_client = llm_client
    
    def switch_model(self, model: str) -> bool:
        """切换模型"""
        if not self._llm_client:
            return False
        
        # 验证模型是否可用
        available = self.list_models()
        if available and model not in available:
            return False
        
        old_model = self._llm_client.model
        self._llm_client.set_model(model)
        
        # 触发回调
        for callback in self._on_changed:
            callback(old_model, model)
        
        return True
    
    def list_models(self) -> list[str]:
        """获取可用模型列表"""
        if self._llm_client:
            return self._llm_client.list_models()
        return []
    
    def get_current_model(self) -> str:
        """获取当前模型"""
        if self._llm_client:
            return self._llm_client.get_model()
        return ""
    
    def on_model_changed(self, callback: Callable) -> None:
        """注册模型变更回调"""
        self._on_changed.append(callback)
```

#### Step 3: AgentLoop 集成

```python
# agent_loop.py

def switch_model(self, model: str) -> bool:
    """切换 LLM 模型"""
    old_model = self.llm.model
    self.llm.set_model(model)
    self.logger.info(f"[bold green]模型已切换: {old_model} → {model}[/bold green]")
    self.audit.write(trace_id="model_switch", event="model_switched", data={
        "old_model": old_model,
        "new_model": model,
    })
    return True

def get_current_model(self) -> str:
    """获取当前模型"""
    return self.llm.model
```

#### Step 4: 斜杠命令

```python
# slash_commands.py

def handle_model_command(agent: AgentLoop, args: str) -> str:
    """处理 /model 命令"""
    args = args.strip()
    
    if not args:
        # 显示当前模型
        return f"当前模型: {agent.get_current_model()}"
    
    # 切换模型
    if agent.switch_model(args):
        return f"✓ 已切换到模型: {args}"
    else:
        return f"✗ 切换失败: 模型 '{args}' 不可用"

def handle_models_command(agent: AgentLoop) -> str:
    """处理 /models 命令"""
    models = agent.llm.list_models()
    current = agent.get_current_model()
    
    if not models:
        return "无法获取模型列表（API 不支持或网络错误）"
    
    lines = ["可用模型:"]
    for m in models:
        marker = " ✓" if m == current else ""
        lines.append(f"  - {m}{marker}")
    
    return "\n".join(lines)
```

---

## 4. 用户交互

### 4.1 命令示例

```bash
# 查看当前模型
you (): /model
当前模型: deepseek-ai/DeepSeek-V3

# 列出可用模型
you (): /models
可用模型:
  - ggml-org/Qwen3-14B-GGUF
  - deepseek-ai/DeepSeek-V3 ✓
  - gpt-4o-mini

# 切换模型
you (): /model ggml-org/Qwen3-14B-GGUF
✓ 已切换到模型: ggml-org/Qwen3-14B-GGUF
```

### 4.2 CLI 参数

```bash
# 启动时指定模型
clude chat --model gpt-4o-mini

# 交互式选择（已实现）
clude chat --select-model
```

---

## 5. 验收标准

- [ ] `/model` 显示当前模型
- [ ] `/model <name>` 切换模型
- [ ] `/models` 列出可用模型
- [ ] 切换后立即生效
- [ ] 审计日志记录切换事件
- [ ] 编译通过且无 lint 错误

---

## 6. 风险与兼容性

| 风险 | 缓解措施 |
|------|---------|
| API 不支持 `/v1/models` | 允许切换到任意模型名，不强制校验 |
| 切换后上下文不兼容 | 提示用户可能需要 `/clear` 清空历史 |
| 模型名拼写错误 | 提供模糊匹配建议 |

---

## 7. 实现进度

| 步骤 | 状态 |
|------|------|
| Step 1: LLM 客户端增强 | ✅ 已完成 |
| Step 2: 模型管理器 | ✅ 已完成 |
| Step 3: AgentLoop 集成 | ✅ 已完成 |
| Step 4: 斜杠命令 | ✅ 已完成 |
| Step 5: 测试验证 | ✅ 已通过编译和导入测试 |

---

## 8. 修改的文件列表

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `src/clude_code/llm/llama_cpp_http.py` | 修改 | 添加 `set_model()`, `get_model()`, `on_model_changed()` |
| `src/clude_code/llm/model_manager.py` | 新建 | 全局模型管理器单例 |
| `src/clude_code/orchestrator/agent_loop/agent_loop.py` | 修改 | 集成 ModelManager，添加 `switch_model()`, `get_current_model()`, `list_available_models()`, `rollback_model()` |
| `src/clude_code/cli/slash_commands.py` | 修改 | 增强 `/model` 命令，新增 `/models` 命令 |
| `src/clude_code/cli/chat_handler.py` | 修改 | 修复 `--select-model` 选择后未同步到 AgentLoop 的 bug |
| `src/clude_code/cli/enhanced_chat_handler.py` | 修改 | 同上 |

---

## 9. Bug 修复记录

### Bug: `--select-model` 选择后模型未生效

**现象**: 用户通过 `clude chat --select-model` 选择模型后，实际 LLM 请求仍使用旧模型。

**根因**: 
- `ChatHandler.__init__` 在创建 `AgentLoop` 时已经初始化了 `self.llm`
- `select_model_interactively()` 是在 `__init__` **之后**调用的
- 虽然 `cfg.llm.model` 被更新了，但 `AgentLoop.llm.model` 未同步

**修复**: 
在 `ChatHandler.select_model_interactively()` 中，检测模型变化后调用 `self.agent.switch_model()` 同步更新

