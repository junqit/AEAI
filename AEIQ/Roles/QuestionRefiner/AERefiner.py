"""
AERefiner - 问题精炼 Flow，继承 AEFlow。

将用户输入的问题改写为更清晰、更完整、更易于 AI 理解的问题。
"""
import logging

from WorkFlows.AEFlow import AEFlow, AEFlowStatus, AEFlowFunctional
from WorkFlows.AEFlowInput import AEFlowInput
from WorkFlows.AEFlowOutput import AEFlowOutput
from Context.Context.AELLMPayload import AELLMPayload
from Roles.AERole import AERole, AE_USER_QUESTION_PREFIX, AE_ROLE, AE_CONTENT

logger = logging.getLogger(__name__)


class AERefiner(AEFlow):
    """问题精炼 Flow：改写用户问题，输出 answer。"""

    def __init__(self, flowOutput: AEFlowOutput):
        super().__init__(flowOutput=flowOutput)
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

    @property
    def outResult_summary(self) -> str:
        """覆写：以统一前缀（AE_USER_QUESTION_PREFIX）返回精炼后的问题。"""
        answer = self._extract_answer(self.outResult) or ""
        return f"{AE_USER_QUESTION_PREFIX}{answer}"

    def startFlow(self, flowInput: AEFlowInput) -> None:
        """启动：交基类置 input，拼装 AELLMPayload 发送。

        - messages: system(title) / system(responsibility) / user(input.content)
        - out_schema: 本 flow 的输出结构（output 已在构造时设置，含 reply 占位，由 LLM 生成精炼后的问题）

        Args:
            flowInput: flow 输入数据（content 即用户原始问题）
        """
        if not super().startFlow(flowInput):
            return

        messages = []
        role_brief = self.role_brief
        if len(role_brief) > 0:
            messages.append({AE_ROLE: AERole.SYSTEM.value, AE_CONTENT: role_brief})
        messages.append({AE_ROLE: AERole.USER.value, AE_CONTENT: self.input.content if self.input else ""})
        # 用本 flow 的 output.out_schema 作 llm_out，由 flowOutput 按 complete 打包成路由信封
        # （ident/title/funcationkey + llm_out）；flow_receive_complete 随机 funcident，回包据此路由
        flow_out = self.flowOutput(AEFlowFunctional.flow_receive_complete)
        payload = AELLMPayload(
            messages=messages,
            out_schema=flow_out.out_schema,
        )
        # 发送前置状态为 complete，注入 out_schema 后回包按 complete 处理
        self.send_llm_payload(payload)
