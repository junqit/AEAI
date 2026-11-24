"""
AERoleAnswer - LLM 作答能力 mixin。

仅提供 LLM 直接作答能力（requestLLMAnswer）；前置链路（角色信息/问题优化/角色选择/任务拆解）
与 flow 编排由宿主 AEOrchestrator 承担。作为 mixin 混入 AEOrchestrator，回包方法落在宿主实例上
（AEFlow 回包按方法名派发，经宿主 self 解析）。回包经基类 receive_summarize_result 完成本 flow。
"""
import logging

from Context.Context.AELLMPayload import AELLMPayload
from Roles.RoleBase.AERoleType import AEConentRole, AE_ROLE
from WorkFlows.FlowWork.AEFlowInfo import AE_CONTENT, AE_IDENT
from WorkFlows.FlowWork.AEFlowDelegate import AEFlowCompletEvent
from Tools.Excutor.AERuntimeExcutor import AEFunctional
from Roles.RoleBase.AERole import AERole

logger = logging.getLogger(__name__)


class AERoleAnswer(AERole):
    """LLM 作答能力 mixin：仅 requestLLMAnswer。前置链路与编排由宿主（AEOrchestrator）承担。"""

    # 请求 LLM 作答；无可作答问题则错误完成闭环。
    def requestLLMAnswer(self) -> bool:
        # 优先用优化后的 goal，没有则用原始问题 content
        answer_target = ""
        if self.input is not None:
            answer_target = self.input.get_goal() or self.input.get_content()
        if not answer_target:
            logger.warning("[%s][d=%s] 无可作答问题，以错误完成本 flow 避免卡死", self.title, self.deepth)
            self.flow_complete(
                {AE_IDENT: self.delegate.ident if self.delegate is not None else self.ident,
                 AE_CONTENT: "无可作答问题"},
                AEFlowCompletEvent.error,
            )
            return False
        messages = []
        role_brief = self.role_brief()
        if len(role_brief) > 0:
            messages.append({AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: role_brief})
        messages.append({
            AE_ROLE: AEConentRole.USER.value,
            AE_CONTENT: f"{answer_target}\n请直接回答上述问题",
        })
        flow_out = self.generateFlowOutput(AEFunctional.receive_summarize_result)
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema, temperature=0.7)
        self.flow_send_llm_request(payload)
        return True

    # 作答/汇总结果回包：最终结论，直接完成 flow
    def receive_summarize_result(self, data: dict) -> bool:
        answer = ""
        if isinstance(data, dict):
            answer = data.get(AE_CONTENT, "") or ""
        elif isinstance(data, str):
            answer = data
        self.flow_complete(
            {AE_IDENT: self.delegate.ident if self.delegate is not None else self.ident,
             AE_CONTENT: answer},
        )
        return True
