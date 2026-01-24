# LLM 命名规范改进实施计划

基于 `LLM_MODULE_NAMING_ANALYSIS.md` 文档分析，本文档记录改进实施过程。

## 实施计划

| 序号 | 任务 | 优先级 | 状态 |
|------|------|--------|------|
| P1 | 完善 Provider 模板 | 高 | ✅ 完成 |
| P2 | 添加 CI 命名检查脚本 | 中 | ✅ 完成 |
| P3 | 重命名 llama_cpp_http.py（可选） | 低 | 跳过 |

---

## P1: 完善 Provider 模板

### 思考过程

**问题分析**:
- 当前新增 Provider 需要手动创建文件，容易遗漏必要属性
- 47 个厂商文件格式略有差异
- 缺少标准化的代码模板

**业界对比**:
- LangChain: 使用 `BaseLLM` 抽象类 + 详细文档
- Dify: 提供 `manifest.yaml` + 代码模板
- LiteLLM: 使用装饰器 + 配置文件

**解决方案**:
1. 创建 `provider_template.py` 示例文件
2. 在 `providers/__init__.py` 添加模板文档字符串
3. 创建 CLI 命令 `clude provider new <name>` 自动生成（可选）

### 实现方案

```python
# 模板文件: providers/_template.py
"""
{Provider Name} 提供商模板

新增厂商时复制此模板并修改。

必填项：
- PROVIDER_ID: 与文件名一致
- PROVIDER_NAME: 显示名称
- PROVIDER_TYPE: cloud | local | aggregator
- REGION: 海外 | 国内 | 通用
- chat(): 核心聊天方法
"""
```

### 验收标准
- [ ] 模板文件包含所有必要属性
- [ ] 模板文件可直接复制使用
- [ ] 文档说明清晰

---

## P2: 添加 CI 命名检查脚本

### 思考过程

**问题分析**:
- 目前没有自动化检查文件命名规范
- 新贡献者可能不了解命名约定
- PR 审查时需要人工检查

**业界对比**:
- 大多数项目使用 pre-commit hooks
- GitHub Actions 可以在 PR 时检查

**解决方案**:
1. 创建 Python 检查脚本 `scripts/check_provider_naming.py`
2. 检查文件名格式
3. 检查 PROVIDER_ID 与文件名一致性
4. 检查必要类属性存在

### 实现方案

检查规则:
1. 文件名必须全小写
2. 只允许字母、数字和下划线
3. 不能以数字开头
4. PROVIDER_ID 必须与文件名一致
5. 必须包含 PROVIDER_NAME、PROVIDER_TYPE、REGION

### 验收标准
- [x] 脚本可独立运行
- [x] 检测到不规范命名时返回非零退出码
- [x] 输出清晰的错误信息
- [x] 支持 --fix 参数提示修复建议

---

## P3: 重命名 llama_cpp_http.py（跳过）

### 决策说明

**不实施原因**:
1. 影响范围大（多处导入引用）
2. 当前命名虽不完美但可接受
3. 重命名收益低于风险

**保持现状**:
- `llama_cpp_http.py` 继续作为通用 HTTP 客户端
- 新代码通过 `LlamaCppHttpClient` 类名访问
- 在文档中说明历史原因

---

## 实施进度

### P1 进度 ✅ 完成
- [x] 创建模板文件 `providers/_template.py`
- [x] 包含完整注释和使用说明
- [x] 语法检查通过

### P2 进度 ✅ 完成
- [x] 创建检查脚本 `scripts/check_provider_naming.py`
- [x] 测试脚本（48 个文件全部通过）
- [x] 修复 `llama_cpp.py` REGION 值
- [ ] 更新 CI 配置（可选，后续添加）

---

**开始时间**: 2026-01-24
**完成时间**: 2026-01-24

---

## 完成汇报

### 新增文件

| 文件 | 用途 | 行数 |
|------|------|------|
| `src/clude_code/llm/providers/_template.py` | Provider 标准模板 | ~280 |
| `scripts/check_provider_naming.py` | 命名规范检查脚本 | ~180 |

### 修复内容

| 文件 | 修改 | 说明 |
|------|------|------|
| `llama_cpp.py` | `REGION = "本地"` → `"通用"` | 符合标准值集合 |

### 验证结果

```
LLM Provider 命名规范检查
============================================================
扫描文件: 48
通过: 48 ✅
失败: 0 
============================================================
✅ 所有 Provider 命名规范检查通过！
```

### 代码健壮性检查

- [x] 模板文件语法正确（`compileall` 通过）
- [x] 检查脚本语法正确（`compileall` 通过）
- [x] 脚本可独立运行
- [x] 支持 `--verbose` 和 `--fix` 参数
- [x] 正确的退出码（0=成功，1=失败）

### 使用说明

```bash
# 运行命名检查
python scripts/check_provider_naming.py

# 显示详细信息（含警告）
python scripts/check_provider_naming.py --verbose

# 显示修复建议
python scripts/check_provider_naming.py --fix

# 新增 Provider 时
# 1. 复制 _template.py
cp src/clude_code/llm/providers/_template.py src/clude_code/llm/providers/my_provider.py
# 2. 修改类名和属性
# 3. 运行检查
python scripts/check_provider_naming.py
```

