"""
AEWorkGroup - 工作组 Flow，继承 AEFlow。

负责完成一个维度 / 目录的目标：接收上游（如 AEAssistant）分配的维度目标，
驱动该维度的工作并输出结果。各工作组相互独立，可并行。
"""
import logging

from WorkFlows.AEFlow import AEFlow, AEFlowFunctional
from WorkFlows.AEFlowInput import AEFlowInput
from WorkFlows.AEFlowOutput import AEFlowOutput
from Context.Context.AELLMPayload import AELLMPayload
from Roles.AERole import AERole, AE_ROLE, AE_CONTENT

logger = logging.getLogger(__name__)


class AEWorkGroup(AEFlow):
    """工作组 Flow：完成单一维度 / 目录的目标。"""

    def __init__(self, flowOutput: AEFlowOutput):
        super().__init__(flowOutput=flowOutput)
        self.title = "Work Group"
        self.responsibility = (
            "负责完成分配给本工作组的一个维度 / 目录目标。\n"
            "要求：\n"
            "1. 仅处理本维度范围内的工作，不越界。\n"
            "2. 输出该维度的结论与产物。\n"
            "3. 与其他工作组保持独立，可并行。"
        )

    def startFlow(self, flowInput: AEFlowInput) -> None:
        """启动：交基类置 input，拼装 AELLMPayload 发送。

        - messages: system(role_brief) / user(input.content)
        - out_schema: 本 flow 的输出结构（output 已在构造时设置，由 LLM 填充）

        Args:
            flowInput: flow 输入数据（content 即本工作组负责的维度目标）
        """
        if not super().startFlow(flowInput):
            return
        messages = []
        role_brief = self.role_brief
        if len(role_brief) > 0:
            messages.append({AE_ROLE: AERole.SYSTEM.value, AE_CONTENT: role_brief})
        messages.append({AE_ROLE: AERole.USER.value, AE_CONTENT: self.input.content if self.input else ""})
        flow_out = self.flowOutput(AEFlowFunctional.flow_receive_complete)
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        self.send_llm_payload(payload)
