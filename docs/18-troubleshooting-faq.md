# 18 | 故障排除与常见问题 (Troubleshooting & FAQ)

> **Status (状态)**: Living Document (持续更新中)  
> **Audience (读者)**: End Users / Developers (最终用户/开发者)  
> **Goal (目标)**: 提供快速定位并解决使用过程中常见工程问题的方案。

---

## 1. LLM 连接与推理 (Connection & Inference)

### 1.1 报错：`ConnectionRefusedError` (无法连接)
- **原因**: 本地模型服务（如 `llama.cpp`, `Ollama`）未启动，或端口不一致。
- **方案**: 
  - 检查服务状态。
  - 在 `~/.clude/config.yaml` 中核对 `base_url` 是否包含 `/v1` 后缀（部分服务商要求）。

### 1.2 LLM 返回空内容或持续换行
- **原因**: 推理参数设置不当（如 `temperature` 过高）或模型量化版本损坏。
- **方案**: 
  - 尝试 `/config` 将 `temperature` 降低至 0.2 以下。
  - 查看 `audit.jsonl` 中的原始响应，确认是否触发了模型的“停止词”。

### 1.3 ReAct 一直“等待中”(ReAct Hang / ReAct 卡住)
- **现象**: TUI 显示 `ReAct 决策/直接回答` 长时间 0%，`llm_request_params` 后没有 `llm_response`。
- **业界常见根因 (Industry Root Causes / 业界常见根因)**:
  - `max_tokens` 配置过大（把“上下文窗口大小”误当作“输出上限”）。
  - 模型服务端超时或卡死（推理负载过高/显存不足/线程数不合理）。
  - UI 未收到失败事件，导致一直显示等待（缺少 `llm_error`）。
- **解决方案 (Fix / 解决)**:
  - 将 `max_tokens` 调整到 512~2048（本项目默认 1024）。
  - 将 `timeout_s` 调整到合理范围（例如 60~120s），并确认 base_url 可达。
  - 查看 `~/.clude/audit.jsonl` 中是否出现 `llm_error` / `timeout`（用于定位根因）。
- **参见 (See Also / 参见)**: [`docs/21-react-hang-analysis.md`](./21-react-hang-analysis.md)

---

## 2. 工具执行 (Tool Execution)

### 2.1 `apply_patch` 冲突 (Patch Conflict)
- **原因**: 模型基于过时的文件快照生成补丁。
- **方案**: 
  - 尝试 `/clear` 清除历史上下文，重新读取该文件。
  - 确保没有其他进程在并发修改同一文件。

### 2.2 `codebase_search` 结果不理想
- **原因**: 索引尚未构建完成，或分块（Chunking）策略不匹配。
- **方案**: 
  - 检查 TUI 面板中的索引进度。
  - 尝试 `/doctor` 运行 RAG 诊断。

---

## 3. 界面与显示 (UI/UX)

### 3.1 TUI 界面字符乱码
- **原因**: 终端不支持 Unicode 或 Rich Markup。
- **方案**: 
  - 推荐使用现代终端（Windows Terminal, iTerm2）。
  - 确保环境变量 `PYTHONIOENCODING=utf-8`。

---

## 4. 相关文档 (See Also)

- **架构总览 (Overview)**: [`docs/00-overview.md`](./00-overview.md)
- **可观测性 (Observability)**: [`docs/12-observability.md`](./12-observability.md)

