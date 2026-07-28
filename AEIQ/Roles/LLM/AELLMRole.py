"""
AELLMRole - LLM 直接作答角色 Flow，继承 AERole。

直接接收问题，请求 LLM 作答，回包经 flow_receive_complete 完成本 flow。
不经角色信息生成、不拆解、不执行脚本——最简的直接作答角色。
"""
import logging

from WorkFlows.AEFlowInput import AEFlowInput
from WorkFlows.AEFlowOutput import AEFlowOutput
from Context.Context.AELLMPayload import AELLMPayload
from Roles.AERoleType import (
    AEConentRole, AE_USER_QUESTION_PREFIX, AE_ROLE, AE_CONTENT, AEFlowRole, get_role_param,
)
from Roles.AERole import AERole
from Tools.Excutor.AERuntimeExcutor import AEFunctional

logger = logging.getLogger(__name__)


class AELLMRole(AERole):
    """LLM 直接作答角色：接收问题 → 请求 LLM → 回包完成 flow。"""

    def __init__(self, flowOutput: AEFlowOutput, ident: str = ""):
        super().__init__(flowOutput=flowOutput, ident=ident)
        self.title = "LLM"
        self.responsibility = "直接接收问题并调用 LLM 作答，不做拆解或脚本执行。"

    def roleDescription(self) -> str:
        """角色描述：返回本角色的职称与职责。"""
        info = get_role_param(AEFlowRole.llm)
        return f"{info.title}：{info.responsibility}"

    def startFlow(self, flowInput: AEFlowInput) -> None:
        """启动：交基类置 input，拼装 AELLMPayload 直接请求 LLM 作答（回包走 flow_receive_complete）。

        - messages: system(role_brief) / system(用户问题，AE_USER_QUESTION_PREFIX 前缀) / user(作答指令)
        - out_schema: 本 flow 的输出结构（output 已在构造时设置，由 LLM 填充）
        - 回包 funcationkey=flow_receive_complete，LLM 填充 AE_ANSWER 后即完成本 flow

        Args:
            flowInput: flow 输入数据（content 即待回答的问题）
        """
        if not super().startFlow(flowInput):
            logger.warning("[%s][%s][d=%s] startFlow 失败：基类未启动（非 default 状态），忽略",
                           type(self).__name__, self.title, self.deepth)
            return
        messages = []
        role_brief = self.role_brief()
        if len(role_brief) > 0:
            messages.append({AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: role_brief})
        question = self.input.content if self.input is not None else ""
        if len(question) > 0:
            messages.append({AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: f"{AE_USER_QUESTION_PREFIX}{question}"})
        messages.append({
            AE_ROLE: AEConentRole.USER.value,
            AE_CONTENT: f"请直接回答{AE_USER_QUESTION_PREFIX}，给出准确、完整的结论。",
        })
        flow_out = self.flowOutput(AEFunctional.flow_receive_complete)
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        self.send_llm_payload(payload)
