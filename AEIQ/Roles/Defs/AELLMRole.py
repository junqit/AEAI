"""
AELLMRole - LLM 直接作答角色 Flow，继承 AERoleExcutor。

与 AERoleExcutor 共用前置优化链路（角色信息 → rolePrompt → 问题优化），区别在于
最后一步不拆解、不执行脚本，而是直接请求 LLM 作答，回包经 flow_receive_complete 完成。
_role()=llm；requestRoleSelect 覆写为直接作答（替代默认的 requestRoleSelect）。
"""
from Context.Context.AELLMPayload import AELLMPayload
from Roles.AERoleType import AEConentRole, AE_USER_QUESTION_PREFIX, AE_ROLE, AEFlowRole
from WorkFlows.FlowWork.AEFlowInfo import AE_CONTENT
from Roles.Defs.AERoleExcutor import AERoleExcutor
from Tools.Excutor.AERuntimeExcutor import AEFunctional


class AELLMRole(AERoleExcutor):
    """LLM 直接作答角色：经角色信息/问题优化后，请求 LLM 作答，回包完成 flow。"""

    @classmethod
    def _role(cls):
        return AEFlowRole.llm

    def roleDescription(self) -> str:
        """角色描述：返回本角色的职称与职责。"""
        return f"{self.title}：{self.responsibility}"

    def requestRoleSelect(self) -> None:
        """llm：不选角色，直接请求 LLM 作答（不拆解、不执行脚本）。回包经 flow_receive_complete 完成本 flow。"""
        messages = []
        role_brief = self.role_brief()
        if len(role_brief) > 0:
            messages.append({AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: role_brief})
        question = self.roleGoal or (self.input.parameter.get(AE_CONTENT, "") if self.input is not None else "")
        if len(question) > 0:
            messages.append({AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: f"{AE_USER_QUESTION_PREFIX}{question}"})
        messages.append({
            AE_ROLE: AEConentRole.USER.value,
            AE_CONTENT: f"请直接回答{AE_USER_QUESTION_PREFIX}",
        })
        flow_out = self.generateFlowOutput(AEFunctional.flow_receive_complete)
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        self.send_llm_payload(payload)
