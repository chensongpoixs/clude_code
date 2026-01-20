# 15 | 安装与部署（可实现规格）(Installation & Deployment Spec)

> **Status (状态)**: Stable Spec (稳定规格)  
> **Audience (读者)**: End Users / DevOps (最终用户/运维)  
> **Goal (目标)**: 提供简单、可靠的安装与更新机制，支持多平台环境。

---

## 1. 安装方式 (Installation Methods)

### 1.1 Python Package (推荐)
适用于开发者环境，基于 `pip` 或 `pipx`。

```bash
# 安装
pip install clude-code

# 安装带 UI 依赖 (Textual)
pip install "clude-code[ui]"

# 安装带 RAG 依赖 (LanceDB)
pip install "clude-code[rag]"
```

### 1.2 源码安装 (Source)
适用于贡献者。

```bash
git clone https://github.com/your-repo/clude-code.git
cd clude-code
pip install -e ".[dev,ui,rag]"
```

---

## 2. 环境依赖 (Prerequisites)

- **OS（操作系统）**: Windows, macOS, Linux
- **Python（Python 版本）**: >= 3.10
- **RAM（内存）**: 
  - 基础运行: < 500MB
  - RAG 索引: 取决于仓库大小 (建议 2GB+)
- **LLM**: 需可访问 OpenAI 兼容接口 (本地 llama.cpp 或 云端 API)

---

## 3. 配置管理 (Configuration)

首次运行时，系统会引导生成 `~/.clude/config.yaml`。

```yaml
llm:
  provider: openai_compat
  base_url: http://localhost:8000/v1
  api_key: sk-xxx

rag:
  enabled: true
  db_path: .clude/vector_db
```

---

## 4. 相关文档 (See Also)

- **架构总览 (Overview)**: [`docs/00-overview.md`](./00-overview.md)
- **运行时规格 (Runtime)**: [`docs/07-runtime-and-terminal.md`](./07-runtime-and-terminal.md)
