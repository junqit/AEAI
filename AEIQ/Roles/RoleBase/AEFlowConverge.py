"""AEFlowConverge - 收敛策略 mixin。

子 flow 全完成时回 _orchestrate 让 LLM 决策（替代 AEFlowDelegateImpl 基类的 summarize_to_llm）。
覆写 receive_flow_complete：completeIdent 委托 super / 否则 _record_completed_sub_tasks + 全完成 _orchestrate
/ 未全完成 super 推进 nextFlow。宿主须提供 _orchestrate（仅 AEOrchestrator 继承）。
"""
import logging

from WorkFlows.FlowWork.AEFlowInput import AEFlowStatus
from Roles.RoleBase.AERole import AERole

logger = logging.getLogger(__name__)


class AEFlowConverge(AERole):
    """收敛策略 mixin：子 flow 全完成回 _orchestrate（替代基类 summarize_to_llm），仅 Orchestrator 继承。"""

    def receive_flow_complete(self, flowOutput) -> bool:
        """子 flow 完成回调：记录子任务目标+结论到 flow_context；全完成回 _orchestrate 走收敛链。

        子 flow 创建时 output.ident 设为父 ident（见 do_decompose / receiveContextNeeded / receiveWorkflow），
        故完成通知 ident==self.ident：
        - completeIdent 非空（gather_context 等一次性回调）：交 super 触发注册方法，不记子任务。
        - 否则（decompose）：记录已 complete 的子 flow 目标+结论（按 ident 去重）；
          全部完成 → _orchestrate（让 LLM 选 synthesize→verify→complete），不走 summarize_to_llm；
          未全完成 → super 推进 nextFlow。
        """
        ident = flowOutput.ident if flowOutput is not None else ""
        if ident == self.ident:
            if flowOutput.completeIdent:
                return super().receive_flow_complete(flowOutput)
            self._record_completed_sub_tasks()
            if self._flows and all(f.status == AEFlowStatus.complete for f in self._flows.values()):
                logger.info("[%s][d=%s] 全部子 flow 完成，回到 _orchestrate 走 synthesize→verify→complete",
                            self.title, self.deepth)
                self._orchestrate()
                return True
            return super().receive_flow_complete(flowOutput)
        return super().receive_flow_complete(flowOutput)

    def _record_completed_sub_tasks(self) -> None:
        """记录所有已 complete 子 flow 的目标与结论到 flow_context（按 ident 去重）。"""
        for sub_ident, sub in self._flows.items():
            if sub.status != AEFlowStatus.complete:
                continue
            goal = (sub.input.get_goal() or sub.input.get_content()) if sub.input else ""
            result = sub.output.outResult or ""
            self.flow_context.record_sub_task(sub_ident, goal, result)
