# LLM 适配模块

负责与后端 LLM 服务（如 `llama.cpp`）进行 HTTP 通信。

## 核心组件
- `llama_cpp_http.py`: 提供统一的对话接口，支持 OpenAI 兼容模式与原生 Completion 模式。

## 模块流程
![LLM Flow](module_flow.svg)

