# Phase 3: CLI 集成 - 厂商/模型管理命令

## 目标

实现用户友好的 CLI 命令，支持：
1. 查看可用厂商列表
2. 切换当前厂商
3. 查看当前厂商的模型列表
4. 切换模型

## 思考过程

### 3.1 现有命令分析

当前已有的 slash 命令：
- `/model <name>` - 切换模型
- `/models` - 列出模型
- `/help` - 帮助

需要新增：
- `/providers` - 列出所有厂商
- `/provider <name>` - 切换厂商
- 增强 `/models` - 显示更多信息

### 3.2 命令设计

#### `/providers` 命令

```
you (): /providers

╭──────────────────────────────────────────────────────────────╮
│                    可用模型厂商 (21)                          │
├──────────────────────────────────────────────────────────────┤
│  序号  │  厂商 ID          │  名称                │  区域    │
├────────┼───────────────────┼─────────────────────┼──────────┤
│  1     │  ★ deepseek       │  DeepSeek           │  国内    │
│  2     │  openai           │  OpenAI             │  海外    │
│  3     │  anthropic        │  Anthropic          │  海外    │
│  ...   │  ...              │  ...                │  ...     │
╰──────────────────────────────────────────────────────────────╯

★ = 当前使用
使用 /provider <id> 切换厂商
```

#### `/provider <name>` 命令

```
you (): /provider openai
✓ 已切换到厂商: OpenAI
  当前模型: gpt-4o
  可用模型: 7 个

you (): /provider unknown
✗ 未知厂商: unknown
  可用厂商: deepseek, openai, anthropic, ...
```

#### 增强 `/models` 命令

```
you (): /models

╭──────────────────────────────────────────────────────────────╮
│             DeepSeek 可用模型 (3)                             │
├──────────────────────────────────────────────────────────────┤
│  模型 ID            │  名称              │  上下文    │  能力   │
├─────────────────────┼────────────────────┼────────────┼─────────┤
│  ★ deepseek-chat    │  DeepSeek Chat     │  64K       │  📞     │
│  deepseek-reasoner  │  DeepSeek R1       │  64K       │         │
│  deepseek-coder     │  DeepSeek Coder    │  64K       │  📞     │
╰──────────────────────────────────────────────────────────────╯

🖼️ = Vision  📞 = Function Call  ★ = 当前使用
```

### 3.3 实现方案

1. **修改 `slash_commands.py`**
   - 添加 `_handle_providers()` 函数
   - 添加 `_handle_provider()` 函数
   - 增强 `_handle_models()` 函数

2. **使用 Rich 库美化输出**
   - 使用 `Table` 组件展示列表
   - 使用颜色区分当前选中项

3. **集成 ModelManager**
   - 调用 `mm.list_providers()` 获取厂商列表
   - 调用 `mm.switch_provider()` 切换厂商
   - 调用 `mm.list_models_info()` 获取模型详情

### 3.4 文件修改计划

| 文件 | 修改内容 |
|------|----------|
| `cli/slash_commands.py` | 添加 `/providers`, `/provider` 命令 |
| `cli/slash_commands.py` | 增强 `/models` 命令显示 |

## 实施步骤

1. ✅ 写思路文档（本文件）
2. ✅ 实现 `/providers` 命令
3. ✅ 实现 `/provider <name>` 命令
4. ✅ 增强 `/models` 命令
5. ✅ 编译检查
6. ✅ 汇报进度

---

## 完成汇报

### 新增命令

| 命令 | 功能 |
|------|------|
| `/providers` | 列出所有可用厂商（21+） |
| `/provider <id>` | 切换到指定厂商 |

### 增强命令

| 命令 | 增强内容 |
|------|----------|
| `/models` | 使用 Rich Table 展示，显示上下文窗口、能力标记（Vision/Function Call） |
| `/help` | 新增厂商/模型分类 |

### 修改文件

- `src/clude_code/cli/slash_commands.py`
  - 新增 `_list_providers()` 函数
  - 新增 `_switch_provider()` 函数
  - 增强 `_list_models()` 函数
  - 更新 `_print_help()` 函数
  - 更新 `handle_slash_command()` 添加新命令处理

### 验证结果

```bash
# 编译检查
python -m compileall -q src/clude_code/cli/slash_commands.py  # ✅ 通过

# Lint 检查
read_lints  # ✅ 无错误
```

