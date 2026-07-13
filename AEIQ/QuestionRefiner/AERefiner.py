"""
AERefiner - 问题精炼 Flow，继承 AEFlow。

将用户输入的问题改写为更清晰、更完整、更易于 AI 理解的问题。
"""
import logging

from WorkFlows.AEFlow import AEFlow, AEFlowStatus
from WorkFlows.AEFlowInput import AEFlowInput
from WorkFlows.AEFlowOutput import AEFlowOutput
from Context.Context.AELLMPayload import AELLMPayload
from Assistant.AERole import AERole
from Excutor.AERuntimeExcutor import AEFunctional

logger = logging.getLogger(__name__)


class AERefiner(AEFlow):
    """问题精炼 Flow：改写用户问题，输出 answer。"""

    def __init__(self, ident: str):
        super().__init__(ident=ident)
        # 职称 / 职责要求
        self.title = "Question Refiner"
        self.responsibility = (
            "将用户输入的问题改写为更清晰、更完整、更易于 AI 理解的问题。\n"
            "要求：\n"
            "1. 保持用户原始意图不变。\n"
            "2. 不增加用户未明确表达的新需求。\n"
            "3. 不进行分析、推理或回答问题。\n"
            "4. 不补充事实信息。\n"
            "5. 只优化表达方式。\n"
            "6. 输出应该直接作为后续 AI 的输入。\n"
            "如果问题已经清晰，则仅做轻微优化。"
        )

    def startFlow(self, flowInput: AEFlowInput, flowOutput: AEFlowOutput) -> None:
        """启动：交基类置 input/output，拼装 AELLMPayload 发送。

        - messages: system(title) / system(responsibility) / user(input.content)
        - out_schema: 本 flow 的输出结构（含 answer 占位，由 LLM 生成精炼后的问题）

        Args:
            flowInput: flow 输入数据（content 即用户原始问题）
            flowOutput: flow 输出结构
        """
        if not super().startFlow(flowInput, flowOutput):
            return

        messages = []
        if self.title:
            messages.append({"role": AERole.SYSTEM.value, "content": self.title})
        if self.responsibility:
            messages.append({"role": AERole.SYSTEM.value, "content": self.responsibility})
        messages.append({"role": AERole.USER.value, "content": self.input.content if self.input else ""})
        # 复用上游传入 output 中的 llm_out 配置，用本 flow 的 ident/title/funcationkey 重新打包；
        # flowOutput 内部按 complete 注册 flow_receive_complete（funcident 随机，回包据此路由）
        flow_out = self.flowOutput(AEFunctional.flow_receive_complete)
        payload = AELLMPayload(
            messages=messages,
            out_schema=flow_out.out_schema,
        )
        # 发送前置状态为 complete，注入 out_schema 后回包按 complete 处理
        self.send_llm_payload(payload)
