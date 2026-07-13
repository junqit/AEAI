"""
AEChat - 聊天 Flow，继承 AEFlow。

接收 AENetQues 网络消息并处理（构建 LLM 请求、驱动子 flow 等）。
"""
import uuid
import logging
from typing import Optional

from WorkFlows.AEFlow import AEFlow
from WorkFlows.AEFlowInput import AEFlowInput
from WorkFlows.AEFlowOutput import AEFlowOutput
from Network.Core.AENetReq import AENetReqInfo
from QuestionRefiner.AERefiner import AERefiner
from Excutor.AERuntimeExcutor import AEFunctional

logger = logging.getLogger(__name__)


class AEChat(AEFlow):
    """聊天 Flow：由 context 构建 input 后交 startFlow 启动"""

    def __init__(self, ident: str):
        super().__init__(ident=ident)
        # 职称
        self.title = "Chat"
        # 触发本 chat 的请求信息（回响应时回填 req，供客户端按 path 路由）
        self.req: Optional[AENetReqInfo] = None
        # 添加首个子 flow：问题精炼（delegate 设为当前 chat，LLM 请求经 chat 向上转发）
        self.refiner = AERefiner(ident=uuid.uuid4().hex)
        self.addFlow(self.refiner)
        self.refiner.set_delegate(self)

    def startFlow(self, flowInput: AEFlowInput, flowOutput: AEFlowOutput) -> None:
        """启动 chat flow：交基类置 input/output 并切到 processing，随后启动首个子 flow。

        - 仅当基类 startFlow 返回 True（成功启动）时，才取首个子 flow（问题精炼）启动
        """
        if not super().startFlow(flowInput, flowOutput):
            return
        next_flow = self.nextFlow()
        if next_flow is not None:
            next_flow.startFlow(flowInput, self.flowOutput(AEFunctional.flow_receive_processing))


