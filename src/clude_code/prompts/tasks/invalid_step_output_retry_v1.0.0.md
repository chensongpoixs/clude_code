---
title: "Invalid Step Output Retry"
version: "1.0.0"
layer: "task"
---

你刚才的输出不符合执行协议。
请立刻重试，并且只输出以下两类之一（严格 JSON，不要 ```，不要解释）：
1) 工具调用 JSON：{"tool":"...","args":{...}}
2) 控制 JSON：{"control":"step_done","summary":"..."} 或 {"control":"replan","reason":"..."}


