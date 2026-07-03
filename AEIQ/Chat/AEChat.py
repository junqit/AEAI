"""
AEChat - 聊天 Flow，继承 AEFlow。

接收 AENetReqQuestion 网络消息并处理（构建 LLM 请求、驱动子 flow 等）。
"""
import logging
from typing import Optional

from WorkFlows.AEFlow import AEFlow, AEFlowStatus
from Network.Core.AENetReq import AENetReqQuestion
from Context.AELLMPayload import AELLMPayload

logger = logging.getLogger(__name__)


class AEChat(AEFlow):
    """聊天 Flow：接收 AENetReqQuestion 消息并处理"""

    def __init__(self, ident: str):
        super().__init__(ident=ident)
        # 最近一次接收的问题消息（按需读取，不参与路由）
        self.question: Optional[AENetReqQuestion] = None
        # 组装好的 LLM 请求（out_schema 取自首个子 flow 的 input_schema）
        self.payload: Optional[AELLMPayload] = None

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
        # 进入处理中
        self.status = AEFlowStatus.processing
        self.question = question
        logger.info(
            "[AEChat:%s] 收到问题 type=%s ident=%s content=%r",
            self.ident, question.type, question.ident, question.content,
        )

        # 组装 AELLMPayload：role=user, content=question.content
        payload = AELLMPayload(
            messages=[{"role": "user", "content": question.content or ""}]
        )
        # 取下一个待执行子 flow，将其 input_schema 赋给 payload.out_schema
        first = self.nextFlow()
        if first is None:
            logger.error("[AEChat:%s] 无可用子 flow，无法设置 out_schema", self.ident)
            return
        payload.out_schema = first.inputSchema()
        self.payload = payload
        # 通过 delegate 发送 payload
        self.send_llm_payload(self.payload)
