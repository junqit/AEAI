"""
AERoleExcuteLLM - LLM 作答能力 mixin。

仅提供 LLM 直接作答能力（requestLLMAnswer）；前置链路（角色信息/问题优化/角色选择/任务拆解）
与 flow 编排由宿主 AERoleExcutor 承担。作为 mixin 混入 AERoleExcutor，回包方法落在宿主实例上
（AEFlow 回包按方法名派发，经宿主 self 解析）。回包经基类 receive_summarize_result 完成本 flow。
"""
import logging

from Context.Context.AELLMPayload import AELLMPayload
from Roles.RoleBase.AERoleType import AEConentRole, AE_ROLE
from WorkFlows.FlowWork.AEFlowInfo import AE_CONTENT, AE_IDENT
from WorkFlows.FlowWork.AEFlowDelegate import AEFlowCompletEvent
from Tools.Excutor.AERuntimeExcutor import AEFunctional

logger = logging.getLogger(__name__)


class AERoleExcuteLLM:
    """LLM 作答能力 mixin：仅 requestLLMAnswer。前置链路与编排由宿主（AERoleExcutor）承担。"""

    # 请求 LLM 作答；无可作答问题则错误完成闭环。
    def requestLLMAnswer(self) -> bool:
        if not (self.input.get_goal() if self.input is not None else ""):
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
        goal = self.input.get_goal() if self.input is not None else ""
        messages.append({
            AE_ROLE: AEConentRole.USER.value,
            AE_CONTENT: f"{goal}\n请直接回答上述问题",
        })
        flow_out = self.generateFlowOutput(AEFunctional.receive_summarize_result)
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        self.flow_send_llm_request(payload)
        return True
