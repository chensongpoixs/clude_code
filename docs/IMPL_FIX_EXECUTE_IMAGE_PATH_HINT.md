# 修复执行阶段图片路径缺失导致错误任务

> **目标**: 让执行阶段的 LLM 知道真实图片路径，避免调用错误路径（如 design.png）
> **状态**: 🔄 进行中

---

## 1. 问题现象

执行阶段 LLM 输出：
```
{"tool": "analyze_image", "args": {"path": "design.png", ...}}
```

但真实路径是：
```
D:/Work/AI/clude_code/img/ctx_102400_12b_rtx5080_16gb.png
```

导致工具执行失败，进入 replan。

---

## 2. 根因分析

1. **执行阶段 prompt 未包含图片路径**  
   LLM 只能猜测路径名称（如 design.png）。

2. **图片数据只在多模态 content 内**  
   工具调用时 LLM 无法直接读取路径字段。

3. **虽有回退机制，但 LLM 仍会持续生成错误路径**  
   回退可修复执行，但会反复触发错误日志与重规划。

---

## 3. 解决方案

### 方案 A（推荐）
在 `execute_step.j2` 中显式提示最近图片路径：

```
【图片路径】：D:/Work/AI/...
如果需要 analyze_image，请优先使用该路径
```

### 方案 B（备选）
在 `AgentLoop` 执行阶段，将图片路径追加到 user_content 中。

---

## 4. 实施步骤

1. 在 `AgentLoop` 维护 `self._last_image_paths`
2. 在执行阶段构建 prompt 时，注入图片路径提示
3. 更新 `execute_step.j2` 模板，增加图片路径区块

---

## 5. 预期效果

修复前：
```
LLM: {"path": "design.png"}
```

修复后：
```
LLM: {"path": "D:/Work/AI/clude_code/img/ctx_...png"}
```

---

## 6. 验证方式

1. 输入：`分析 @image:真实路径`
2. 观察 execute_step prompt 是否包含图片路径
3. LLM 是否使用正确路径调用 analyze_image


