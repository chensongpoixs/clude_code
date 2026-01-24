# 删除 `llama_cpp_http.py`（消除与 llama.cpp 厂商命名冲突）实施方案

## 1. 背景与目标

### 背景

当前项目同时存在：

- **厂商实现**：`src/clude_code/llm/providers/llama_cpp.py`（llama.cpp Provider）
- **通用功能模块**：`src/clude_code/llm/llama_cpp_http.py`（历史命名，但实际是通用 HTTP Client 的兼容层）

即使我们已经把核心实现迁移到 `http_client.py`，**文件名 `llama_cpp_http.py` 仍然会在概念上与 llama.cpp 厂商冲突**，造成：

- 新人误解（以为是 llama.cpp 专用 client）
- 文档/搜索噪音（`llama_cpp` 和 `llama_cpp_http` 混在一起）
- 后续扩展/对齐业界命名时不够干净

### 目标

- **删除物理文件** `src/clude_code/llm/llama_cpp_http.py`（彻底消除文件名冲突）
- **保持 import 兼容**：仍允许 `import clude_code.llm.llama_cpp_http`（通过 `sys.modules` alias）
- 文档与打包清单同步更新

---

## 2. 现状审计（删除前）

### 2.1 运行时依赖检查

在 `src/` 中搜索：

- ✅ **未发现** `from clude_code.llm.llama_cpp_http import ...` 的运行时引用
- ✅ `llama_cpp_http.py` 当前仅为 re-export 兼容层（无业务逻辑）

### 2.2 与配置的关系

`LLMConfig.provider = "llama_cpp_http"` 是**“provider id 字符串”**，用于选择后端模式，**不依赖 Python 模块文件名**。

因此删除 `llama_cpp_http.py` 不会影响配置字段的语义（只影响历史 import 路径）。

---

## 3. 业界迁移方式对比

### 3.1 直接删除 vs 兼容 alias

| 方案 | 描述 | 优点 | 风险 |
|------|------|------|------|
| 直接删除 | 删除文件，不做兼容 | 最干净 | 外部用户旧 import 直接崩 |
| 保留文件 | 文件保留为兼容层 | 兼容最好 | 文件名冲突仍存在（不满足目标） |
| ✅ 删除 + `sys.modules` alias | 删除文件，但在包 `__init__` 注入 alias | 文件名冲突消失 + 兼容 import | 需要写明迁移与限制 |

业界常用做法是在包入口做**别名导出/模块重定向**，实现“移除物理文件但保持历史 import 路径可用”。

---

## 4. 实施计划（模块功能视角）

### 4.1 修改点

1. **`src/clude_code/llm/__init__.py`**
   - 增加 `sys.modules` alias：把 `clude_code.llm.llama_cpp_http` 指向 `clude_code.llm.http_client`
2. **删除** `src/clude_code/llm/llama_cpp_http.py`
3. **更新文档**
   - `src/clude_code/llm/README.md`：不再列出 `llama_cpp_http.py` 文件
4. **更新打包清单（若仓库内提交了 egg-info）**
   - `src/clude_code.egg-info/SOURCES.txt`：移除 `llm/llama_cpp_http.py`

### 4.2 兼容细节（关键）

在 `llm/__init__.py` 中加入：

- `import importlib, sys`
- `sys.modules["clude_code.llm.llama_cpp_http"] = importlib.import_module("clude_code.llm.http_client")`

这样即便文件不存在，`import clude_code.llm.llama_cpp_http` 仍会返回 `http_client` 模块对象。

---

## 5. 风险与缓解

### 5.1 风险清单

| 风险 | 说明 | 等级 | 缓解 |
|------|------|------|------|
| 外部旧 import 失败 | 外部项目若直接 import 子模块 | 中 | ✅ `sys.modules` alias 保持兼容 |
| alias 生效时机 | 子模块 import 会先执行包 `__init__` | 低 | Python 导入机制保证：导入子模块前会加载包 |
| 文档与现实不一致 | README/egg-info 未同步 | 低 | 同步更新并加 grep 校验 |

### 5.2 回滚方案

- 方案 A：撤销 alias 并恢复文件（git revert）
- 方案 B：保留 alias 的同时恢复文件（兼容更强，但回到命名冲突）

---

## 6. 验收标准

- [ ] 全项目 `python -m compileall -q src` ✅
- [ ] 全仓 `grep -r "from .*llama_cpp_http import" src` 为 0 ✅
- [ ] 兼容性：`import clude_code.llm.llama_cpp_http` ✅
- [ ] `llm/README.md` 不再列出该文件 ✅

---

**创建时间**：2026-01-24


