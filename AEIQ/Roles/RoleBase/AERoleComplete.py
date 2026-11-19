"""AERoleComplete - 完成输出能力 mixin（收敛链 complete 阶段，终态）。

把最终结果写入 flow.output（不发 LLM 请求，直接输出）。结果优先级：显式 result > verify 通过的综合候选 synthesis；
收敛链未走完（无 synthesis）时退化用 input.goal/content 兜底防卡死。
作为 mixin 混入 AEOrchestrator。
"""
import logging

from WorkFlows.FlowWork.AEFlowInfo import AE_IDENT, AE_CONTENT
from Roles.RoleBase.AERole import AERole

logger = logging.getLogger(__name__)


class AERoleComplete(AERole):
    """完成输出能力 mixin：把最终结果写入 flow.output（终态，不发 LLM 请求）。"""

    def requestComplete(self, result: str = "") -> None:
        """输出最终结果到 flow.output。

        结果优先级：显式 result > verify 通过的综合候选 synthesis；
        无 synthesis 时退化用 input.goal/content 兜底防卡死（告警）。
        """
        if not result:
            result = self.flow_context.synthesis or ""
        if not result:
            logger.warning("[%s][d=%s] complete 无综合候选，退化用 input 兜底（建议先 verify→synthesize→complete）",
                           self.title, self.deepth)
            result = (self.input.get_goal() if self.input is not None else "") or \
                   (self.input.get_content() if self.input is not None else "")
        self.flow_complete(
            {AE_IDENT: self.delegate.ident if self.delegate is not None else self.ident,
             AE_CONTENT: result},
        )
