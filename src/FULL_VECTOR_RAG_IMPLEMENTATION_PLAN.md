# 全量 Vector RAG 系统实现详细规划 (Full Vector RAG Plan)

本规划旨在为 clude-code 引入工业级的代码语义检索能力，支持处理超大规模代码库。

---

## 1. 索引构建流水线 (Indexing Pipeline)

### 1.1 扫描与预处理
- 遍历工作区，尊重 `.gitignore` 规则。
- 难点：<span style="color:red">**超大规模文件扫描性能**：在包含数十万文件的 Monorepo 中，扫描文件元数据并判断是否需要更新索引，若处理不好会导致极高的磁盘 IO 压力。</span>

### 1.2 智能代码分块 (AST-aware Chunking)
- 放弃固定长度切分，采用 `tree-sitter` 解析代码结构。
- 策略：按类（Class）、函数（Function）、方法（Method）进行逻辑切分。
- 难点：<span style="color:red">**代码逻辑完整性**：如何在切分时保留上下文（例如函数上方的装饰器、注释、所属类名），并处理嵌套极深的复杂代码块，防止向量语义丢失。</span>

### 1.3 异步向量化 (Background Embedding)
- 调用本地轻量级模型（如 `bge-small-en-v1.5`）生成 384 维向量。
- 难点：<span style="color:red">**本地算力争抢**：Embedding 计算是计算密集型的。如果与 `llama.cpp` 主推理进程同时运行，会导致风扇狂转且对话响应极慢。必须实现精细的 CPU 亲和性调度或低优先级后台线程。</span>

---

## 2. 存储与检索层 (Storage & Retrieval)

### 2.1 嵌入式向量库 (LanceDB)
- 使用 `LanceDB` 直接将索引存储在 `.clude/index/` 目录下。
- 支持混合搜索（Vector Search + Full-text Search）。

### 2.2 混合召回算法 (Hybrid Search)
- 结合语义相似度与关键词命中得分。
- 难点：<span style="color:red">**得分归一化与加权**：如何科学地分配向量得分与关键词得分的权重，防止“文不对题”的语义结果覆盖了精确的符号匹配。</span>

---

## 3. 动态更新机制 (Incremental Sync)

### 3.1 变更感知
- 监听 `apply_patch` 事件或文件系统变动（watchdog）。
- 难点：<span style="color:red">**实时索引一致性**：Patch 修改代码后，向量库必须立即失效并更新受影响的 Chunk。对于频繁改动场景，频繁的写操作可能导致索引损坏或严重的写放大。</span>

---

## 4. Agent 接入策略 (Agent Integration)

### 4.1 自动注入 vs. 显式工具
- **方案 A**：新增 `search_semantic` 工具，由模型主动调用。
- **方案 B**：Agent 思考时自动进行 Top-K 检索并注入 Context。
- 难点：<span style="color:red">**Context Window 噪音控制**：RAG 召回的片段往往带有大量“相似但无关”的代码。如果一股脑塞给模型，会严重稀释注意力，导致模型遵循指令的能力下降。</span>

---

## 5. 阶段性路线图 (Roadmap)

| 阶段 | 目标 | 关键产出 |
| :--- | :--- | :--- |
| **第一阶段** | 基础检索 | 引入 LanceDB，实现全量代码固定块向量化。 |
| **第二阶段** | 质量优化 | 引入 tree-sitter，实现基于语法的智能分块。 |
| **第三阶段** | 实时性增强 | 实现 Patch 后的增量索引热更新。 |
| **第四阶段** | 性能调优 | 实现 Hybrid Search 与本地 Embedding 资源隔离。 |

