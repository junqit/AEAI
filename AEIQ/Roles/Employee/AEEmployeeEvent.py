"""
AEEmployeeEvent - 员工（Employee）工作步骤事件，继承 AEFlow。

定义员工 Flow 在一次任务中经历的各个工作步骤（类常量），供流程编排、状态记录与日志标识使用。
本类继承 AEFlow，便于后续按需承载工作步骤相关行为。
"""
from WorkFlows.AEFlow import AEFlow


class AEEmployeeEvent(AEFlow):
    """员工工作步骤事件（继承 AEFlow）；各步骤以类常量定义。"""

    roleInfo = "roleInfo"                        # 生成自身角色信息（title / responsibility）
    optimizePrompt = "optimizePrompt"            # 生成问题优化提示
    optimizeInputOptimize = "optimizeInputOptimize"  # 执行任务，得到最终结果 / 需确认信息
    complete = "complete"                        # 完成（结果回传上游）
