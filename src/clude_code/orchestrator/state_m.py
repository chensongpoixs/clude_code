from __future__ import annotations

from enum import Enum


class AgentState(str, Enum):
    """
    显式状态机（阶段 3：规划-执行）。

    说明：
    - 用于事件上报（--live UI）与审计/追踪，避免"只靠日志猜测状态"。
    - 状态转换：INTAKE -> PLANNING -> EXECUTING -> VERIFYING -> DONE
    - 异常路径：EXECUTING -> RECOVERING -> PLANNING (重规划)
    """

    INTAKE = "INTAKE"              # 接收用户输入
    PLANNING = "PLANNING"          # 生成/重规划计划
    EXECUTING = "EXECUTING"        # 按步骤执行工具
    VERIFYING = "VERIFYING"        # 最终验证阶段
    RECOVERING = "RECOVERING"      # 从失败中恢复（重规划前）
    BLOCKED = "BLOCKED"            # 依赖未满足，等待
    DONE = "DONE"                  # 任务完成


