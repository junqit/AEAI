"""
AERefiner - 问题精炼 Flow，继承 AERole。

将用户输入的问题改写为更清晰、更完整、更易于 AI 理解的问题，随后直接创建一个
AERoleExcutor 作为后续执行 flow（跳过角色选择），经 delegate 添加并以 startFlow 事件启动。
"""
import logging

from WorkFlows.AEFlowInput import AEFlowInput
from WorkFlows.AEFlowOutput import AEFlowOutput
from WorkFlows.AEFlowInfo import AE_IDENT, AE_ANSWER
from WorkFlows.AEFlowDelegate import AEFlowCompletEvent
from Context.Context.AELLMPayload import AELLMPayload, llm_generate
from Roles.AERoleType import AEConentRole, AE_USER_QUESTION_PREFIX, AE_ROLE, AE_CONTENT, AEFlowRole
from Roles.AERole import AERole
from Roles.AERoleExcutor import AERoleExcutor

logger = logging.getLogger(__name__)


class AERefiner(AERole):
    """问题精炼 Flow：改写用户问题，输出 answer，并直接派发 AERoleExcutor 执行。"""

    def __init__(self, flowOutput: AEFlowOutput, ident: str = ""):
        super().__init__(flowOutput=flowOutput, ident=ident)
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
        # 问题转换后的内容（精炼后的问题）：由 receiveOptimizeInput 从回包提取并存储
        self._refinedQuestion: str = ""

    def outResult_summary(self) -> str:
        """覆写：以统一前缀（AE_USER_QUESTION_PREFIX）返回精炼后的问题。"""
        answer = self.outResult.get(AE_ANSWER, "") if isinstance(self.outResult, dict) else ""
        return f"{AE_USER_QUESTION_PREFIX}{answer}"

    def receiveOptimizeInput(self, data: dict) -> bool:
        """接收优化后的问题：存入 _refinedQuestion，直接创建 AERoleExcutor 经 delegate 添加并以
        startFlow 事件启动（跳过角色选择），由 delegate 据事件 startFlow 该执行 flow。

        Args:
            data: 回包内层 llm_out，形如 {AE_ANSWER: <优化后的问题>}；若直接为字符串则视为问题

        Returns:
            bool: 当前数据处理是否完成（True=已处理）
        """
        result = data.get(AE_ANSWER) if isinstance(data, dict) else None
        if result is None and isinstance(data, str):
            result = data
        self._refinedQuestion = result or ""
        logger.info(
            "[AEFlow:%s][%s] 收到优化后的问题:\n%s",
            self.ident, self.title, self._refinedQuestion,
        )
        if self.delegate is None:
            logger.warning("[AERefiner:%s] delegate 未设置，无法添加 AERoleExcutor", self.ident)
            return True
        # 直接创建 AERoleExcutor，完成回程路由回 delegate（父 flow）；顶层设为 expert，自上而下逐层分解
        delegate_ident = self.delegate.ident
        excutor = AERoleExcutor(
            flowOutput=AEFlowOutput({AE_IDENT: delegate_ident, AE_ANSWER: llm_generate("任务结论")}),
        )
        excutor.role = AEFlowRole.expert
        self.delegate.receive_add_flow(excutor)
        # 完成 refiner 自身：置 complete、写 outResult，并以 startFlow 事件向上通知，
        # delegate 据此 startFlow 该 AERoleExcutor（input 取精炼后的问题）
        self.flow_receive_complete(
            {AE_IDENT: excutor.ident, AE_ANSWER: self._refinedQuestion},
            AEFlowCompletEvent.startFlow,
        )
        return True

    def startFlow(self, flowInput: AEFlowInput) -> None:
        """启动：交基类置 input，拼装 AELLMPayload 发送。

        - messages: system(title) / system(responsibility) / user(input.content)
        - out_schema: 本 flow 的输出结构（output 已在构造时设置，含 reply 占位，由 LLM 生成精炼后的问题）

        Args:
            flowInput: flow 输入数据（content 即用户原始问题）
        """
        if not super().startFlow(flowInput):
            logger.warning("[AERefiner:%s] startFlow 失败：基类未启动（非 default 状态），忽略", self.ident)
            return

        self.requestOptimizeInput()
