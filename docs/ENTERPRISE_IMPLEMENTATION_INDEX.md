# 企业落地增强版 - 代码入口索引表

> 文档目的：盘点当前代码中与 `project_id`/隔离/注册表/审批流/沙箱 相关的入口与调用链，  
> 为 Phase 0~4 的改造提供精确落点。

---

## 1. 当前路径结构（改造前）

```
{workspace_root}/.clude/
├── logs/
│   ├── app.log           # 应用日志
│   ├── audit.jsonl       # 审计日志
│   └── trace.jsonl       # 追踪日志
├── sessions/             # 会话存储
│   ├── {session_id}.json
│   └── latest.json
├── markdown/             # webfetch 缓存
└── vector_db/            # 向量数据库（可选）
```

---

## 2. 目标路径结构（引入 project_id 后）

```
{workspace_root}/.clude/
├── projects/
│   ├── default/           # project_id="default"（向后兼容）
│   │   ├── logs/
│   │   │   ├── app.log
│   │   │   ├── audit.jsonl
│   │   │   └── trace.jsonl
│   │   ├── sessions/
│   │   ├── cache/
│   │   │   └── markdown/
│   │   └── vector_db/
│   └── {custom_project}/  # 自定义 project_id
│       └── ...
└── registry/              # 全局注册表（跨项目共享）
    └── intents.yaml
```

---

## 3. 代码入口索引表

### 3.1 路径生成相关（需改造为 ProjectPaths）

| 模块 | 当前路径 | 文件 | 关键函数/类 | 改造点 |
| :--- | :--- | :--- | :--- | :--- |
| 审计日志 | `.clude/logs/audit.jsonl` | `src/clude_code/observability/audit.py` | `AuditLogger.__init__` (L26-30) | 路径计算改用 ProjectPaths |
| 追踪日志 | `.clude/logs/trace.jsonl` | `src/clude_code/observability/trace.py` | `TraceLogger.__init__` (L29-33) | 路径计算改用 ProjectPaths |
| 应用日志 | `.clude/logs/app.log` | `src/clude_code/observability/logger.py` | `get_logger()` (L183-185) | 路径计算改用 ProjectPaths |
| 会话存储 | `.clude/sessions/` | `src/clude_code/cli/session_store.py` | `_sessions_dir()` (L19-20) | 路径计算改用 ProjectPaths |
| 缓存目录 | `.clude/markdown/` | `src/clude_code/tooling/tools/webfetch.py` | `_get_cache_dir()` (L95-110) | 路径计算改用 ProjectPaths |
| 向量数据库 | `.clude/vector_db` | `src/clude_code/config/config.py` | `RAGConfig.db_path` (L212-214) | 配置支持 project_id 插值 |
| Doctor 临时文件 | `.clude/doctor.tmp` | `src/clude_code/cli/doctor_cmd.py` | `run_doctor()` (L77) | 路径计算改用 ProjectPaths |

### 3.2 CLI 入口（需增加 --project-id）

| 命令 | 文件 | 关键函数 | 改造点 |
| :--- | :--- | :--- | :--- |
| `clude chat` | `src/clude_code/cli/main.py` | `chat()` | 增加 `--project-id` option |
| `clude doctor` | `src/clude_code/cli/doctor_cmd.py` | `run_doctor()` | 透传 project_id |
| `clude models` | `src/clude_code/cli/info_cmds.py` | `run_models_list()` | 可选：按 project 显示模型偏好 |
| `clude config` | `src/clude_code/cli/main.py` | `config()` | 可选：project 级配置覆写 |

### 3.3 AgentLoop 核心（需透传 project_id）

| 模块 | 文件 | 关键类/函数 | 改造点 |
| :--- | :--- | :--- | :--- |
| AgentLoop 初始化 | `src/clude_code/orchestrator/agent_loop/agent_loop.py` | `AgentLoop.__init__` | 增加 `project_id` 参数 |
| AuditLogger 初始化 | `src/clude_code/observability/audit.py` | `AuditLogger.__init__` | 接收 project_id |
| TraceLogger 初始化 | `src/clude_code/observability/trace.py` | `TraceLogger.__init__` | 接收 project_id |
| 事件写入 | `audit.py` / `trace.py` | `write()` | 事件 data 增加 project_id 字段 |

### 3.4 Intent Registry（新增模块）

| 模块 | 计划路径 | 说明 |
| :--- | :--- | :--- |
| Schema 定义 | `src/clude_code/orchestrator/registry/schema.py` | Pydantic: ProjectConfig, IntentSpec |
| 加载器 | `src/clude_code/orchestrator/registry/loader.py` | YAML 加载 + mtime 热加载 |
| 路由器 | `src/clude_code/orchestrator/registry/router.py` | IntentRouter.get_intent() |
| 示例配置 | `.clude/registry/intents.yaml` | 用户可编辑的意图注册表 |

### 3.5 配置相关

| 配置项 | 文件 | 说明 |
| :--- | :--- | :--- |
| `logging.file_path` | `config/config.py` L128 | 支持 `{project_id}` 占位符 |
| `rag.db_path` | `config/config.py` L213 | 支持 `{project_id}` 占位符 |
| `web.cache_dir` | `config/tools_config.py` L215 | 支持 `{project_id}` 占位符 |

---

## 4. 调用链图示

```
CLI (main.py)
 └─> chat(--project-id=xxx)
      └─> AgentLoop.__init__(session_id, project_id)
           ├─> AuditLogger(workspace_root, session_id, project_id)
           ├─> TraceLogger(workspace_root, session_id, project_id)
           ├─> get_logger(workspace_root, project_id)
           ├─> IntentRegistry.load(workspace_root)          # 全局
           └─> ProjectPaths(workspace_root, project_id)     # 新增
                ├─> logs_dir()      -> .clude/projects/{project_id}/logs/
                ├─> sessions_dir()  -> .clude/projects/{project_id}/sessions/
                ├─> cache_dir()     -> .clude/projects/{project_id}/cache/
                └─> vector_db_dir() -> .clude/projects/{project_id}/vector_db/
```

---

## 5. 向后兼容策略

1. **默认 project_id**：如果用户不传 `--project-id`，默认使用 `"default"`。
2. **旧数据迁移**：
   - 检测 `.clude/logs/` 是否存在（旧结构）
   - 如果存在，提示用户可选迁移到 `.clude/projects/default/logs/`
   - 或直接保持旧路径不动（仅新 project 使用新结构）
3. **配置兼容**：`logging.file_path` 如果不包含 `{project_id}` 占位符，保持原样。

---

## 6. Phase 0 完成度与不足

### 已完成（代码已落地）
- CLI `--project-id`（`chat`）
- `AgentLoop` 接收 `project_id` 并传递到 audit/trace
- `ProjectPaths` 统一路径计算模块
- `AuditLogger` / `TraceLogger` / `SessionStore` 路径隔离
- Intent Registry（schema/loader/router + 示例配置）

### 仍需补齐（代码存在空洞或未接入）
- **project_id 未贯穿所有 CLI**：`doctor/models/config` 等命令尚未透传 `project_id`。
- **日志路径未统一**：`get_logger()` 仍使用 `cfg.logging.file_path`，尚未由 `ProjectPaths` 统一生成。
- **webfetch 缓存路径未接入 project_id**：仍使用 `web.cache_dir` 配置值。
- **配置占位符未实现**：`logging.file_path` / `rag.db_path` / `web.cache_dir` 仍无法解析 `{project_id}`。
- **Intent Registry 未接入 AgentLoop**：路由结果未实际影响 prompt/tools/risk_level。
- **注册表热加载未接入运行时**：`AgentLoop` 当前未持有 `IntentRegistry` 实例。

---

## 7. 下一步（Phase 0 任务清单）

- [x] Step 1: 代码入口索引（本文档）
- [x] Step 2a: CLI 增加 `--project-id`
- [x] Step 2b: AgentLoop 增加 `project_id` 属性
- [x] Step 2c: 存储路径隔离
- [x] Step 3: 抽象 `ProjectPaths` 模块
- [x] Step 4: Intent Registry MVP

