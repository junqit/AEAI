"""
AETask - 原子任务执行 Flow，继承 AERoleExcutor。

执行一个原子性任务：角色信息生成 → 问题优化 → 执行类型判定 → 脚本/直接作答。
与 AERoleExcutor 的区别：AETask 不做目标拆解（跳过 requestDecompose），优化后直接执行。
由 employee 层 receiveDecompose 在下一层为 task 时创建，是层级分解的最底层执行单元。
"""
import logging

from WorkFlows.AEFlowOutput import AEFlowOutput
from WorkFlows.AEFlowInfo import AE_ANSWER, AE_CONFIRM
from Roles.AERoleType import AEFlowRole
from Roles.AERoleExcutor import AERoleExcutor

logger = logging.getLogger(__name__)


class AETask(AERoleExcutor):
    """原子任务执行 Flow：不拆解，优化后直接执行（脚本/直接作答）。"""

    def __init__(self, flowOutput: AEFlowOutput, ident: str = ""):
        super().__init__(flowOutput=flowOutput, ident=ident)
        self.role = AEFlowRole.task
        self.title = "Task"
        self.responsibility = (
            "执行一个原子性任务。"
            "调用模型或工具完成该任务的检索 / 分析 / 生成 / 转换等环节，"
            "产出可被上游直接整合的结构化结果；不再向下拆解。"
        )

    def receiveOptimizeInput(self, data: dict) -> bool:
        """接收优化后的问题：存入 optimizePromptResult，直接执行（跳过 requestDecompose）。

        - AE_ANSWER 非空：优化后的问题，存入 self.optimizePromptResult，直接调 requestQuestionType 执行。
        - AE_CONFIRM 非空：需确认信息，仅记录。

        Args:
            data: 回包内层 llm_out，形如 {AE_ANSWER: <优化后的问题>, AE_CONFIRM: <需确认信息>}

        Returns:
            bool: 当前数据处理是否完成（True=已处理）
        """
        result = data.get(AE_ANSWER) if isinstance(data, dict) else None
        if result is None and isinstance(data, str):
            result = data
        confirm = data.get(AE_CONFIRM) if isinstance(data, dict) else None
        confirm = (confirm or "").strip() if isinstance(confirm, str) else ""
        if confirm:
            logger.info("[AETask:%s] 收到需确认信息:\n%s", self.ident, confirm)
            return True
        self.optimizePromptResult = result or ""
        logger.info("[AETask:%s] 收到优化后的问题:\n%s", self.ident, self.optimizePromptResult)
        # 原子任务：不拆解，直接执行（脚本/直接作答）
        self.requestQuestionType()
        return True
