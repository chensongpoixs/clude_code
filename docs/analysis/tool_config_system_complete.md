# 工具配置系统完整重构

> **重构日期**：2026-01-19
> **重构目标**：为所有工具模块添加独立的配置文件支持
> **参考模块**：weather.py

---

## 1. 重构目标

### 1.1 主要目标
1. **统一配置架构**：为所有工具模块创建独立的配置类
2. **配置检查**：在每个工具中添加启用/禁用检查
3. **日志控制**：每个工具可独立控制日志写入行为
4. **向后兼容**：保持现有配置系统的兼容性

### 1.2 符合规范
- `docs/CODE_SPECIFICATION.md` 3.1 模块配置统一管理
- `docs/CODE_SPECIFICATION.md` 4. 日志与调试

---

## 2. 配置类设计

### 2.1 天气工具配置（已存在）
```python
class WeatherToolConfig(BaseModel):
    enabled: bool = True
    api_key: str = ""
    default_units: str = "metric"
    default_lang: str = "zh_cn"
    timeout_s: int = 10
    cache_ttl_s: int = 300
    log_to_file: bool = True
```

### 2.2 文件工具配置
```python
class FileToolConfig(BaseModel):
    enabled: bool = True
    log_to_file: bool = True
```

### 2.3 目录工具配置
```python
class DirectoryToolConfig(BaseModel):
    enabled: bool = True
    log_to_file: bool = True
```

### 2.4 命令工具配置
```python
class CommandToolConfig(BaseModel):
    enabled: bool = True
    timeout_s: int = 30
    log_to_file: bool = True
```

### 2.5 搜索工具配置
```python
class SearchToolConfig(BaseModel):
    enabled: bool = True
    timeout_s: int = 30
    max_results: int = 1000
    log_to_file: bool = True
```

### 2.6 网络工具配置
```python
class WebToolConfig(BaseModel):
    enabled: bool = True
    timeout_s: int = 30
    max_content_length: int = 50000
    log_to_file: bool = True
```

### 2.7 补丁工具配置
```python
class PatchToolConfig(BaseModel):
    enabled: bool = True
    log_to_file: bool = True
```

### 2.8 显示工具配置
```python
class DisplayToolConfig(BaseModel):
    enabled: bool = True
    max_content_length: int = 10000
    log_to_file: bool = True
```

### 2.9 提问工具配置
```python
class QuestionToolConfig(BaseModel):
    enabled: bool = True
    log_to_file: bool = True
```

### 2.10 仓库地图工具配置
```python
class RepoMapToolConfig(BaseModel):
    enabled: bool = True
    log_to_file: bool = True
```

### 2.11 技能工具配置
```python
class SkillToolConfig(BaseModel):
    enabled: bool = True
    log_to_file: bool = True
```

### 2.12 任务工具配置
```python
class TaskToolConfig(BaseModel):
    enabled: bool = True
    log_to_file: bool = True
```

---

## 3. 实施内容

### 3.1 配置文件扩展

**修改文件**：`src/clude_code/tooling/config.py`

**新增内容**：
- 11 个新的工具配置类
- 12 个便捷的获取函数
- 更新了 `set_tool_configs()` 函数以提取所有配置
- 更新了 `ToolConfigs` 类

### 3.2 主配置类更新

**修改文件**：`src/clude_code/config.py`

**新增内容**：
- 导入所有新的工具配置类
- 在 `CludeConfig` 中添加所有工具配置字段

### 3.3 日志助手更新

**修改文件**：`src/clude_code/tooling/logger_helper.py`

**更新内容**：
- `init_tool_logger_from_config()` 函数支持所有工具的 `log_to_file` 配置

### 3.4 工具模块更新

**已更新的工具模块（16个）**：

1. ✅ **read_file.py** - 文件读取工具
   - 添加 `get_file_config()` 检查
   - 启用状态验证

2. ✅ **write_file.py** - 文件写入工具
   - 添加 `get_file_config()` 检查
   - 启用状态验证

3. ✅ **list_dir.py** - 目录列表工具
   - 添加 `get_directory_config()` 检查
   - 启用状态验证

4. ✅ **glob_search.py** - 全局搜索工具
   - 添加 `get_directory_config()` 检查
   - 启用状态验证

5. ✅ **run_cmd.py** - 命令执行工具
   - 添加 `get_command_config()` 检查
   - 启用状态验证

6. ✅ **grep.py** - 搜索工具
   - 添加 `get_search_config()` 检查
   - 启用状态验证

7. ✅ **webfetch.py** - 网页抓取工具
   - 添加 `get_web_config()` 检查
   - 启用状态验证

8. ✅ **patching.py** - 补丁工具
   - 添加 `get_patch_config()` 检查
   - 启用状态验证

9. ✅ **display.py** - 显示工具
   - 添加 `get_display_config()` 检查
   - 启用状态验证

10. ✅ **question.py** - 提问工具
    - 添加 `get_question_config()` 检查
    - 启用状态验证

11. ✅ **repo_map.py** - 仓库地图工具
    - 添加 `get_repo_map_config()` 检查
    - 启用状态验证

12. ✅ **search.py** - 网页搜索工具
    - 添加 `get_search_config()` 检查
    - 启用状态验证

13. ✅ **skill.py** - 技能加载工具
    - 添加 `get_skill_config()` 检查
    - 启用状态验证

14. ✅ **task_agent.py** - 任务代理工具
    - 添加 `get_task_config()` 检查
    - 启用状态验证

15. ✅ **todo_manager.py** - 任务管理工具
    - 添加 `get_task_config()` 检查
    - 启用状态验证

16. ✅ **weather.py** - 天气工具（已更新使用新的配置系统）

### 3.5 示例配置文件更新

**修改文件**：`clude.example.yaml`

**新增内容**：
- 所有工具的配置示例
- 详细的注释说明
- 合理的默认值

---

## 4. 配置示例

### 4.1 完整配置示例

```yaml
# 文件操作工具配置（read_file, write_file）
file:
  enabled: true                         # 是否启用文件操作工具
  log_to_file: true                     # 是否将文件操作日志写入文件

# 目录操作工具配置（list_dir, glob_search）
directory:
  enabled: true                         # 是否启用目录操作工具
  log_to_file: true                     # 是否将目录操作日志写入文件

# 命令执行工具配置（run_cmd）
command:
  enabled: true                         # 是否启用命令执行工具
  timeout_s: 30                         # 命令执行超时时间（秒）
  log_to_file: true                     # 是否将命令执行日志写入文件

# 搜索工具配置（grep, search）
search:
  enabled: true                         # 是否启用搜索工具
  timeout_s: 30                         # 搜索超时时间（秒）
  max_results: 1000                     # 搜索最大结果数量
  log_to_file: true                     # 是否将搜索日志写入文件

# 网络工具配置（webfetch, search）
web:
  enabled: true                         # 是否启用网络工具
  timeout_s: 30                         # 网络请求超时时间（秒）
  max_content_length: 50000             # 最大内容长度（字符）
  log_to_file: true                     # 是否将网络工具日志写入文件
```

### 4.2 工具禁用示例

```yaml
# 禁用网络相关工具
web:
  enabled: false

# 禁用命令执行（安全考虑）
command:
  enabled: false
```

---

## 5. 实现原理

### 5.1 配置检查逻辑

每个工具在执行前都会检查配置：

```python
def some_tool(...):
    # 检查工具是否启用
    config = get_tool_config()
    if not config.enabled:
        _logger.warning("[ToolName] 工具已被禁用")
        return ToolResult(False, error={"code": "E_TOOL_DISABLED", "message": "tool is disabled"})
    # ... 正常执行逻辑
```

### 5.2 日志配置逻辑

日志系统根据工具类型自动选择配置：

```python
def init_tool_logger_from_config(module_name: str, cfg: Any) -> logging.Logger:
    # 根据模块名确定配置
    if "weather" in module_name:
        log_to_file = tool_configs.weather.log_to_file
    elif "read_file" in module_name or "write_file" in module_name:
        log_to_file = tool_configs.file.log_to_file
    # ... 其他工具的配置映射
```

### 5.3 错误响应

当工具被禁用时，返回标准错误：

```json
{
    "ok": false,
    "error": {
        "code": "E_TOOL_DISABLED",
        "message": "tool is disabled"
    }
}
```

---

## 6. 验证结果

### 6.1 配置加载测试

```bash
# 测试配置加载
conda run -n claude_code python -c "
from clude_code.config import CludeConfig
from clude_code.tooling.config import set_tool_configs, get_file_config, get_command_config
cfg = CludeConfig()
set_tool_configs(cfg)
print('File config:', get_file_config().enabled, get_file_config().log_to_file)
print('Command config:', get_command_config().enabled, get_command_config().timeout_s)
"

# 输出结果：
# File config: True True
# Command config: True 30
```

### 6.2 工具功能测试

```bash
# 测试工具功能
conda run -n claude_code python -c "
from clude_code.tooling.tools.read_file import read_file
from pathlib import Path
result = read_file(workspace_root=Path('.'), max_file_read_bytes=1000, path='README.md', limit=3)
print('Read file test:', result.ok)
"

# 输出结果：
# Read file test: True
# [ReadFile] 开始读取文件: README.md, offset=None, limit=3
# [ReadFile] 读取成功: README.md, 返回行数: 3
```

---

## 7. 架构优势

### 7.1 灵活性
- **工具级控制**：可以独立启用/禁用任何工具
- **细粒度配置**：每个工具都有自己的超时、限制等参数
- **日志控制**：可以为不同工具设置不同的日志行为

### 7.2 安全性
- **安全禁用**：可以禁用潜在危险的工具（如命令执行）
- **网络控制**：可以禁用所有网络相关功能
- **访问控制**：通过配置实现工具级别的访问控制

### 7.3 可维护性
- **统一接口**：所有工具使用相同的配置检查模式
- **集中管理**：所有配置在一个地方定义和管理
- **向后兼容**：不影响现有代码的正常运行

### 7.4 可观测性
- **详细日志**：每个工具都有自己的日志前缀和级别
- **错误追踪**：工具禁用时会记录警告日志
- **调试友好**：可以通过配置控制日志输出

---

## 8. 相关文件

### 8.1 新增/修改文件
- `src/clude_code/tooling/config.py` - 新增 11 个配置类和获取函数
- `src/clude_code/config.py` - 添加工具配置字段
- `src/clude_code/tooling/logger_helper.py` - 更新日志初始化逻辑
- `src/clude_code/tooling/tools/*.py` - 16 个工具模块添加配置检查
- `clude.example.yaml` - 添加所有工具配置示例

### 8.2 影响范围
- **工具模块**：16 个工具模块
- **配置系统**：主配置类和工具配置系统
- **日志系统**：工具级日志控制
- **示例配置**：完整配置示例

---

## 9. 总结

本次重构成功为所有工具模块添加了独立的配置支持：

✅ **16 个工具模块** 全部添加了配置检查和日志控制
✅ **11 个配置类** 涵盖了所有工具类型
✅ **统一接口** 所有工具使用相同的配置模式
✅ **灵活控制** 可以独立管理每个工具的行为
✅ **向后兼容** 不影响现有功能
✅ **完整文档** 提供了详细的配置示例

现在可以通过配置文件精确控制每个工具的行为，包括启用/禁用状态、超时设置、日志输出等，大大提升了系统的灵活性和安全性。

---

**重构完成时间**：2026-01-19
**状态**：✅ 已完成

