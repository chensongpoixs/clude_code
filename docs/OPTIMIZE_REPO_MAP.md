# repo_map 工具优化思考过程

**创建时间**: 2026-01-24  
**工具模块**: `src/clude_code/tooling/tools/repo_map.py`  
**优化目标**: Token效率优化、代码效率提升、健壮性增强

---

## 一、当前实现分析

### 1.1 代码结构

当前 `repo_map.py` 包含以下主要功能：
1. `generate_repo_map()` - 主入口函数，生成仓库图谱
2. 使用 ctags 扫描符号
3. 计算文件权重（基于深度和符号数量）
4. 筛选核心文件（前 50 个）
5. 渲染 Markdown 格式的图谱

### 1.2 当前问题

#### 问题1：每次调用都重新运行 ctags ⚠️

**当前实现**:
- 每次调用 `generate_repo_map()` 都重新运行 ctags
- 对于大型项目，ctags 可能需要几秒甚至几十秒
- 浪费资源，影响用户体验

**优化方向**:
- 缓存 ctags 输出结果（基于文件修改时间）
- 增量更新：只重新扫描修改过的文件

#### 问题2：没有使用 .gitignore

**当前实现**:
- 硬编码排除列表：`.git`, `node_modules`, `venv`, `.venv`, `__pycache__`, `build`, `dist`, `.clude`
- 没有读取 `.gitignore` 文件

**优化方向**:
- 读取 `.gitignore` 文件
- 合并硬编码列表和 `.gitignore` 规则

#### 问题3：ctags 输出没有缓存

**当前实现**:
- ctags 输出每次都重新解析
- 对于大型项目，解析可能需要几秒

**优化方向**:
- 缓存解析后的符号数据
- 基于文件修改时间判断缓存有效性

#### 问题4：权重计算可能不够准确

**当前实现**:
- 权重计算：`base_weight = 10.0 / depth`
- 每增加一个符号，权重增加 0.5

**优化方向**:
- 考虑文件大小、修改时间等因素
- 使用更复杂的权重算法

### 1.3 Token效率分析

**当前实现**:
```markdown
# 核心代码架构图谱 (Core Repo Map)
📁 Project Root/
  📄 file1.py
    └─ [C] MyClass (L10)
    └─ [F] my_function (L20)
```

**Token消耗估算**:
- 每个文件: ~20-30 tokens
- 每个符号: ~10-15 tokens
- 50 个文件，每个 8 个符号: ~5,000-7,500 tokens

**如果包含不需要的文件**:
- 包含测试文件: 浪费 ~1,000 tokens
- 包含文档文件: 浪费 ~500 tokens

**Token节省**: 使用 `.gitignore` 过滤，节省 ~20% ✅

---

## 二、业界最佳实践调研

### 2.1 Sourcegraph

**仓库图谱策略**:
1. 使用 LSP 或 Tree-sitter 解析代码
2. 增量更新索引
3. 缓存符号数据

**优势**:
- 快速（增量更新）
- 准确（语法解析）
- 支持多语言

### 2.2 GitHub Copilot

**代码索引策略**:
1. 使用 Tree-sitter 解析代码
2. 后台异步构建索引
3. 缓存索引数据

**优势**:
- 不阻塞用户操作
- 快速响应
- 准确

### 2.3 Claude Code

**仓库图谱策略**:
1. 使用 ctags 或 LSP 扫描符号
2. 增量更新
3. 智能过滤（基于文件重要性）

**优势**:
- 快速
- 准确
- 智能过滤

### 2.4 业界总结

| 方案 | 优势 | 劣势 | 适用场景 |
|------|------|------|----------|
| ctags 缓存 | 快速、简单 | 需要额外工具 | 大多数场景 |
| 增量更新 | 性能优化 | 实现复杂 | 大型项目 |
| LSP/Tree-sitter | 最准确 | 需要解析器 | IDE 集成 |

**推荐方案**: **ctags 缓存 + 增量更新 + .gitignore 支持**

---

## 三、优化方案设计

### 3.1 添加 ctags 输出缓存

**方案**: 缓存 ctags 输出结果（基于文件修改时间）

**代码示例**:
```python
import hashlib
import pickle
from pathlib import Path

_cache_dir = Path.home() / ".clude" / "cache"
_cache_file = _cache_dir / "repo_map_cache.pkl"

def _get_cache_key(workspace_root: Path) -> str:
    """生成缓存键（基于工作区路径）。"""
    return hashlib.md5(str(workspace_root.resolve()).encode()).hexdigest()

def _load_ctags_cache(workspace_root: Path) -> tuple[list[dict], float] | None:
    """加载缓存的 ctags 输出。"""
    if not _cache_file.exists():
        return None
    
    try:
        with open(_cache_file, "rb") as f:
            cache_data = pickle.load(f)
            cache_key = _get_cache_key(workspace_root)
            if cache_key in cache_data:
                cached_symbols, cached_mtime = cache_data[cache_key]
                # 检查缓存有效性（基于工作区修改时间）
                workspace_mtime = max(
                    (p.stat().st_mtime for p in workspace_root.rglob("*") if p.is_file()),
                    default=0
                )
                if workspace_mtime <= cached_mtime:
                    return cached_symbols, cached_mtime
    except Exception:
        pass
    
    return None

def _save_ctags_cache(workspace_root: Path, symbols: list[dict]) -> None:
    """保存 ctags 输出到缓存。"""
    _cache_dir.mkdir(parents=True, exist_ok=True)
    cache_key = _get_cache_key(workspace_root)
    workspace_mtime = max(
        (p.stat().st_mtime for p in workspace_root.rglob("*") if p.is_file()),
        default=0
    )
    
    try:
        cache_data = {}
        if _cache_file.exists():
            with open(_cache_file, "rb") as f:
                cache_data = pickle.load(f)
        cache_data[cache_key] = (symbols, workspace_mtime)
        with open(_cache_file, "wb") as f:
            pickle.dump(cache_data, f)
    except Exception as e:
        _logger.debug(f"[RepoMap] 保存缓存失败: {e}")
```

### 3.2 添加 .gitignore 支持

**方案**: 读取 `.gitignore` 文件，合并到 ctags 排除列表

**代码示例**:
```python
def _get_exclude_patterns(workspace_root: Path) -> list[str]:
    """获取排除模式列表（合并硬编码和 .gitignore）。"""
    exclude_patterns = [
        ".git", "node_modules", "venv", ".venv",
        "__pycache__", "build", "dist", ".clude",
        "*.json", "*.md", "tests"
    ]
    
    # 读取 .gitignore
    gitignore_path = workspace_root / ".gitignore"
    if gitignore_path.exists():
        try:
            with open(gitignore_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if line.startswith("!"):
                        continue  # 简化：不支持否定规则
                    exclude_patterns.append(line)
        except Exception as e:
            _logger.debug(f"[RepoMap] 读取 .gitignore 失败: {e}")
    
    return exclude_patterns
```

### 3.3 优化权重计算

**方案**: 考虑文件大小、修改时间等因素

**代码示例**:
```python
def _calculate_file_weight(file_path: Path, symbol_count: int, workspace_root: Path) -> float:
    """计算文件权重（考虑深度、符号数量、文件大小、修改时间）。"""
    # 基础权重：深度越浅，权重越高
    depth = len(file_path.relative_to(workspace_root).parts)
    base_weight = 10.0 / depth
    
    # 符号数量权重
    symbol_weight = symbol_count * 0.5
    
    # 文件大小权重（大文件可能更重要）
    try:
        file_size = file_path.stat().st_size
        size_weight = min(file_size / 10000, 5.0)  # 最大 5.0
    except OSError:
        size_weight = 0
    
    # 修改时间权重（最近修改的文件可能更重要）
    try:
        mtime = file_path.stat().st_mtime
        import time
        days_since_modify = (time.time() - mtime) / 86400
        time_weight = max(0, 5.0 - days_since_modify / 30)  # 30 天内修改的文件权重更高
    except OSError:
        time_weight = 0
    
    return base_weight + symbol_weight + size_weight + time_weight
```

---

## 四、预期效果评估

### 4.1 Token效率

**优化前（包含不需要的文件）**:
- 50 个文件（包含 10 个测试文件）: ~7,500 tokens
- 浪费 ~1,500 tokens

**优化后（使用 .gitignore 过滤）**:
- 40 个文件: ~6,000 tokens
- **节省**: ~1,500 tokens（20%）✅

### 4.2 代码效率

**优化前（每次重新运行 ctags）**:
- ctags 执行: ~10-30秒（大型项目）
- 解析输出: ~1-2秒
- 总时间: ~11-32秒

**优化后（使用缓存）**:
- 检查缓存: ~0.1秒
- 读取缓存: ~0.5秒
- 总时间: ~0.6秒

**性能提升**: 20-50倍 ✅

### 4.3 用户体验

**优化前**:
- 每次调用都需要等待 ctags 执行
- 返回可能包含不需要的文件

**优化后**:
- 缓存加速，响应更快
- 自动过滤不需要的文件
- 权重计算更准确

**用户体验提升**: 显著 ✅

---

## 五、实施计划

### 步骤1：添加 ctags 输出缓存

1. 实现缓存加载和保存函数
2. 检查缓存有效性（基于文件修改时间）
3. 集成到 `generate_repo_map()` 函数中

### 步骤2：添加 .gitignore 支持

1. 实现 `.gitignore` 解析函数
2. 合并到 ctags 排除列表
3. 更新 ctags 命令参数

### 步骤3：优化权重计算

1. 实现新的权重计算函数
2. 考虑文件大小、修改时间等因素
3. 更新权重计算逻辑

### 步骤4：测试验证

1. 单元测试：测试缓存机制
2. 集成测试：在 conda 环境中测试
3. 性能测试：对比优化前后性能

---

## 六、风险评估

### 6.1 功能风险

**风险**: 缓存可能过期，导致返回过时的数据

**缓解措施**:
- 基于文件修改时间判断缓存有效性
- 提供手动清除缓存的选项
- 添加充分的测试用例

### 6.2 性能风险

**风险**: 缓存文件可能很大，占用磁盘空间

**缓解措施**:
- 限制缓存大小（如最多 100MB）
- 定期清理过期缓存
- 压缩缓存数据

### 6.3 兼容性风险

**风险**: 添加新功能可能影响现有调用

**缓解措施**:
- 所有新功能都有默认值
- 保持向后兼容
- 充分测试所有场景

---

## 七、下一步行动

1. ✅ 完成思考过程文档（当前步骤）
2. ⏳ 实施代码优化
3. ⏳ 编写/更新测试用例
4. ⏳ 在 conda 环境中测试
5. ⏳ 生成优化报告

---

## 八、业界参考

### 8.1 Sourcegraph

- 使用 LSP 或 Tree-sitter 解析代码
- 增量更新索引
- 缓存符号数据

### 8.2 GitHub Copilot

- 使用 Tree-sitter 解析代码
- 后台异步构建索引
- 缓存索引数据

### 8.3 Claude Code

- 使用 ctags 或 LSP 扫描符号
- 增量更新
- 智能过滤（基于文件重要性）

---

**文档状态**: 思考过程完成，准备实施

