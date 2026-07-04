"""
AEChat - 聊天 Flow，继承 AEFlow。

接收 AENetReqQuestion 网络消息并处理（构建 LLM 请求、驱动子 flow 等）。
"""
import uuid
import logging
from typing import Optional

from WorkFlows.AEFlow import AEFlow, AEFlowStatus
from Network.Core.AENetReq import AENetReqQuestion
from Context.AELLMPayload import AELLMPayload
from QuestionRefiner.AERefiner import AERefiner
from Assistant.AERole import AERole

logger = logging.getLogger(__name__)


class AEChat(AEFlow):
    """聊天 Flow：接收 AENetReqQuestion 消息并处理"""

    def __init__(self, ident: str):
        super().__init__(ident=ident)
        # 职称
        self.title = "Chat"
        # 最近一次接收的问题消息（按需读取，不参与路由）
        self.question: Optional[AENetReqQuestion] = None
        # 添加首个子 flow：问题精炼
        self.addFlow(AERefiner(ident=uuid.uuid4().hex))

    def receiveQuestion(self, question: AENetReqQuestion) -> None:
        """
        接收 AENetReqQuestion 消息进行处理。

        - 校验消息非空
        - 切换状态为 processing
        - 组装 AELLMPayload（role=user，content=question.content）
        - 取首个子 flow，将其 input_schema 赋给 payload.out_schema
        - 通过 delegate 发送 payload

        Args:
            question: 网络问题消息体（type / ident / content）
        """
        if question is None:
            logger.error("[AEChat:%s] 收到的 AENetReqQuestion 为空", self.ident)
            return
        # 收到消息即进入 inputSchemed
        self.status = AEFlowStatus.inputSchemed
        self.question = question
        # 用 input 持有 question 的结构（role=user, content=question.content）
        self.input = {"role": AERole.USER.value, "content": question.content or ""}
        logger.info(
            "[AEChat:%s] 收到问题 type=%s ident=%s content=%r",
            self.ident, question.type, question.ident, question.content,
        )

        self.nextFlow().autoConfigInputSchema()
