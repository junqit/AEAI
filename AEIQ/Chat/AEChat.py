"""
AEChat - 聊天 Flow，继承 AEFlow。

接收 AENetQues 网络消息并处理（构建 LLM 请求、驱动子 flow 等）。
"""
import uuid
import logging
from typing import Optional

from WorkFlows.AEFlow import AEFlow, AEFlowStatus
from WorkFlows.AEFlowInput import AEFlowInput
from WorkFlows.AEFlowOutput import AEFlowOutput
from Network.Core.AENetReq import AENetQues, AENetReqInfo
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
        # 触发本 chat 的请求信息（回响应时回填 req，供客户端按 path 路由）
        self.req: Optional[AENetReqInfo] = None
        # 添加首个子 flow：问题精炼
        self.addFlow(AERefiner(ident=uuid.uuid4().hex))

    def receiveQuestion(self, question: AENetQues) -> None:
        """
        接收 AENetQues 消息：校验非空，持有 question 与 input，并启动首个子 flow。

        Args:
            question: 网络问题消息体（type / ident / content）
        """
        if question is None:
            logger.error("[AEChat:%s] 收到的 AENetQues 为空", self.ident)
            return
        # 收到消息即进入 processing
        self.status = AEFlowStatus.processing
        self.question = question
        self.input = AEFlowInput(content=question.content or "")
        logger.info(
            "[AEChat:%s] 收到问题 type=%s ident=%s content=%r",
            self.ident, question.type, question.ident, question.content,
        )
        # 取首个子 flow，以 input 启动（output 由子 flow 自身确定/填充）
        next_flow = self.nextFlow()
        if next_flow is not None:
            next_flow.startFlow(self.input, AEFlowOutput())
