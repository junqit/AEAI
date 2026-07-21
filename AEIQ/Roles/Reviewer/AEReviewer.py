"""
AEReviewer - 评审者 Flow，继承 AERole。

对产出进行审查与验收：依据验收标准检查正确性 / 完整性 / 一致性，给出通过或返工意见。
"""
import logging

from WorkFlows.AEFlow import AEFlowFunctional
from WorkFlows.AEFlowInput import AEFlowInput
from WorkFlows.AEFlowOutput import AEFlowOutput
from Context.Context.AELLMPayload import AELLMPayload
from Roles.AERole import AEConentRole, AE_ROLE, AE_CONTENT
from Roles.AEBaseRole import AERole

logger = logging.getLogger(__name__)


class AEReviewer(AERole):
    """评审者 Flow：审查并验收产出。"""

    def __init__(self, flowOutput: AEFlowOutput, ident: str = ""):
        super().__init__(flowOutput=flowOutput, ident=ident)
        self.title = "Reviewer"
        self.responsibility = (
            "对产出进行审查与验收。\n"
            "要求：\n"
            "1. 依据验收标准检查正确性 / 完整性 / 一致性。\n"
            "2. 识别事实错误、逻辑漏洞、遗漏维度与越界内容。\n"
            "3. 不合格给出修改意见要求返工，或判定通过。\n"
            "4. 不替代执行角色产出内容，仅行使审查与通过权。"
        )

    def startFlow(self, flowInput: AEFlowInput) -> None:
        """启动：交基类置 input，拼装 AELLMPayload 发送。

        - messages: system(role_brief) / user(input.content)
        - out_schema: 本 flow 的输出结构（output 已在构造时设置，由 LLM 填充）

        Args:
            flowInput: flow 输入数据（content 即待审查的产出及验收标准）
        """
        if not super().startFlow(flowInput):
            return
        messages = []
        role_brief = self.role_brief()
        if len(role_brief) > 0:
            messages.append({AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: role_brief})
        messages.append({AE_ROLE: AEConentRole.USER.value, AE_CONTENT: self.input.content if self.input else ""})
        flow_out = self.flowOutput(AEFlowFunctional.flow_receive_complete)
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        self.send_llm_payload(payload)
