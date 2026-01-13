# 代码健壮性检查报告（含分析流程与改进点）

## 1. 我是如何做健壮性检查的（流程）

### 1.1 先画“关键链路”
- **CLI**：参数解析、异常对用户可见、日志落盘是否稳定
- **编排器**：消息规范化、工具生命周期、失败重试/重规划、状态机事件
- **工具层**：输入校验、路径沙箱、安全策略、错误码统一
- **验证闭环**：命令白名单、环境脱敏、错误解析、选择性测试
- **RAG**：索引线程、增量机制、可恢复性、护栏、查询接口一致性

### 1.2 再找“最容易出事故”的点

- **状态写入时机错误**：例如“扫描时就写入 mtime”，索引失败会导致永久漏索引（业界常见坑）
- **依赖缺失的降级策略**：例如向量库/embedding 库未安装时是否进入死循环刷日志
- **接口不一致**：例如 A 模块期望向量，B 模块传文本，导致运行时异常
- **后台线程生命周期**：退出/异常时是否可控，是否会吞异常或占用资源

### 1.3 最后做“最小改动的加固”

优先采用：
- **可恢复（state 持久化）**
- **可降级（disable 而不是 crash/死循环）**
- **可观测（错误要同时落盘+屏幕可见）**
- **一致性（接口/数据结构单一真相）**

---

## 2. 本次检查发现的问题与修复

### 2.1 RAG 索引：mtime 提前写入导致“索引失败后永久漏索引”
- **问题**：`IndexerService._scan_modified_files` 在扫描阶段就把 `mtime` 写入 state；如果后续 `_index_file` 因依赖缺失/解析失败退出，下一轮不会再次尝试索引（除非文件再次修改）。
- **修复**：改为“扫描只发现，不落盘 mtime”；**仅在索引成功后**写入 `mtime/hash`。

### 2.2 RAG 索引：向量库依赖缺失时会反复报错占用资源
- **问题**：`VectorStore` 依赖 `lancedb/pyarrow`；缺失时 `_connect()` 会抛异常，后台线程进入 error-sleep 循环，持续产生噪声。
- **修复**：索引写入阶段捕获异常，设置状态为 `disabled: vector_store_unavailable` 并停止索引线程（降级停用）。

### 2.3 Embedding：device/providers 参数版本差异导致崩溃风险
- **问题**：不同 fastembed 版本对 `providers` 支持不一致，直接传参可能 `TypeError`。
- **修复**：best-effort 传 `providers`，捕获 `TypeError` 自动回退到默认 provider，并输出 warning。

### 2.4 语义检索：缺少 cfg.rag.enabled 开关的硬拦截
- **问题**：RAG 禁用时仍可能触发语义检索。
- **修复**：`semantic_search` 增加 `cfg.rag.enabled` 检查，返回 `E_RAG_DISABLED`。

---

## 3. 仍建议补齐的健壮性增强（下一步）

- <span style="color:red">**AST-aware 分块**</span>：启发式 chunking 上限明显，建议 Tree-sitter/LSP range 分块（召回质量提升最大）。
- <span style="color:red">**Watcher 机制**</span>：mtime 在某些 Windows/网络盘场景会抖动，Watcher 更稳（或“mtime+size+hash”组合）。
- **索引并发与背压**：线程池 + 队列长度限制，避免大仓库瞬时占满 CPU/GPU。
- **向量维度治理**：embedding_model 变更时应分表/分库，避免 schema 兼容问题。

---

## 4. 事故复盘：输入“你好啊”触发规划并因 llama.cpp 超时失败

### 4.1 现象（你提供的日志）
- 用户输入：`你好啊`
- 意图识别：`UNCERTAIN`
- 进入规划阶段：触发一次 LLM 请求
- llama.cpp 返回：`status=500 body=proxy error: Connection timed out`

### 4.2 根因分解（分两类）

#### A. 策略/分类问题（为什么会进入规划）
- `IntentClassifier` 原本存在“短文本问候”启发式分流，但被注释掉，导致 `你好啊` 落到 `UNCERTAIN`。
- `AgentLoop` 的决策门只对 `GENERAL_CHAT/CAPABILITY_QUERY` 关闭规划；对 `UNCERTAIN` 没做短文本兜底，因此错误进入规划。

#### B. 运行环境/链路问题（为什么 LLM 会超时）
- `proxy error: Connection timed out` **不是业务 JSON 错误**，而是网络/代理/服务端模型加载阻塞导致的超时。
- 常见原因：
  - llama.cpp server 未启动/端口不可达
  - 反向代理到后端失败（代理配置/系统环境变量）
  - 服务端模型未加载完成或卡在 GPU/CPU 初始化（导致 upstream 超时）

### 4.3 本次修复（已落地）
- **启发式分类恢复**：对 `你好/你好啊/hi/hello/在吗` 等短文本直接归类为 `GENERAL_CHAT`，避免不必要的大模型请求。
- **UNCERTAIN 短文本兜底**：即使分类为 UNCERTAIN，若疑似问候也强制关闭规划。
- **LLM 请求异常增强**：`llama_cpp_http` 明确区分 timeout/request_error，使上层能输出更明确的排障提示。

