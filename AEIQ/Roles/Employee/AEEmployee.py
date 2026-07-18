"""
AEEmployee - 员工 Flow，继承 AEFlow。

完成单一流水线的工作：承接上游分配的一条流水线，调用 LLM / Tools 执行其各环节，
产出可被上游整合的结构化结果。
"""
import logging

from WorkFlows.AEFlow import AEFlow, AEFlowFunctional
from WorkFlows.AEFlowInput import AEFlowInput
from WorkFlows.AEFlowOutput import AEFlowOutput
from Context.Context.AELLMPayload import AELLMPayload
from Roles.AERole import AEConentRole, AE_ROLE, AE_CONTENT

logger = logging.getLogger(__name__)


class AEEmployee(AEFlow):
    """员工 Flow：完成单一流水线的工作。"""

    def __init__(self, flowOutput: AEFlowOutput, ident: str = ""):
        super().__init__(flowOutput=flowOutput, ident=ident)
        self.title = "Employee"
        self.responsibility = (
            "完成单一流水线的工作。\n"
            "要求：\n"
            "1. 仅负责本流水线的执行，不跨流水线、不跨维度规划与决策。\n"
            "2. 调用模型或工具完成流水线各环节（检索 / 分析 / 生成 / 转换等）。\n"
            "3. 产出可直接被上游整合的结构化结果。\n"
            "4. 遇到不明确处向上回传，由工作组或专家裁决。"
        )

    def startFlow(self, flowInput: AEFlowInput) -> None:
        """启动：交基类置 input，拼装 AELLMPayload 发送。

        - messages: system(role_brief) / user(input.content)
        - out_schema: 本 flow 的输出结构（output 已在构造时设置，由 LLM 填充）

        Args:
            flowInput: flow 输入数据（content 即工作组下发的子任务）
        """
        if not super().startFlow(flowInput):
            return
        messages = []
        role_brief = self.role_brief
        if len(role_brief) > 0:
            messages.append({AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: role_brief})
        messages.append({AE_ROLE: AEConentRole.USER.value, AE_CONTENT: self.input.content if self.input else ""})
        flow_out = self.flowOutput(AEFlowFunctional.flow_receive_complete)
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        self.send_llm_payload(payload)
