"""
AEChat - 聊天 Flow，继承 AEFlow。

接收 AENetQues 网络消息并处理（构建 LLM 请求、驱动子 flow 等）。
"""
import uuid
import logging
from typing import Optional

from WorkFlows.AEFlow import AEFlow, AEFlowStatus
from Network.Core.AENetReq import AENetQues
from Context.Context.AELLMPayload import AELLMPayload
from QuestionRefiner.AERefiner import AERefiner

logger = logging.getLogger(__name__)


class AEChat(AEFlow):
    """聊天 Flow：接收 AENetQues 消息并处理"""

    def __init__(self, ident: str):
        super().__init__(ident=ident)
        # 职称
        self.title = "Chat"
        # 最近一次接收的问题消息（按需读取，不参与路由）
        self.question: Optional[AENetQues] = None
        # 添加首个子 flow：问题精炼
        self.addFlow(AERefiner(ident=uuid.uuid4().hex))

    def receiveQuestion(self, question: AENetQues) -> None:
        """
        接收 AENetQues 消息进行处理。

        - 校验消息非空
        - 切换状态为 processing
        - 组装 AELLMPayload（role=user，content=question.content）
        - 取首个子 flow，将其 input_schema 赋给 payload.out_schema
        - 通过 delegate 发送 payload

        Args:
            question: 网络问题消息体（type / ident / content）
        """
        if question is None:
            logger.error("[AEChat:%s] 收到的 AENetQues 为空", self.ident)
            return
        # 收到消息即进入 inputSchemed
        self.status = AEFlowStatus.inputSchemed
        self.question = question
        # 用 input 持有待转换的内容（question.content），后续由 flow_complete_input_schemed
        # 作为 role=system 的 content，转换成 next_flow.inputSchema() 结构
        self.input = question.content or ""
        logger.info(
            "[AEChat:%s] 收到问题 type=%s ident=%s content=%r",
            self.ident, question.type, question.ident, question.content,
        )

        self.nextFlow().autoConfigInputSchema()
