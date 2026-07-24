"""
AEChat - 聊天 Flow，继承 AEFlow。

接收 AENetQues 网络消息并处理（构建 LLM 请求、驱动子 flow 等）。
"""
import logging
from typing import Optional

from WorkFlows.AEFlow import AEFlow, AE_IDENT, AE_ANSWER
from WorkFlows.AEFlowInput import AEFlowInput
from WorkFlows.AEFlowOutput import AEFlowOutput
from Network.Core.AENetReq import AENetReqInfo
from Roles.QuestionRefiner.AERefiner import AERefiner
from Roles.Assistant.AEAssistant import AEAssistant

logger = logging.getLogger(__name__)


class AEChat(AEFlow):
    """聊天 Flow：由 context 构建 input 后交 startFlow 启动"""

    def __init__(self, flowOutput: AEFlowOutput, ident: str = ""):
        super().__init__(flowOutput=flowOutput, ident=ident)
        # 职称
        self.title = "Chat"
        # 触发本 chat 的请求信息（回响应时回填 req，供客户端按 path 路由）
        self.req: Optional[AENetReqInfo] = None
        # 添加首个子 flow：问题精炼（delegate 设为当前 chat，LLM 请求经 chat 向上转发）
        # refiner 的 output.ident 填本 chat.ident，使其完成时路由回本 chat 的 receive_flow_result
        from Context.Context.AELLMPayload import llm_generate
        refiner_output = AEFlowOutput({AE_IDENT: self.ident, AE_ANSWER: llm_generate("精炼后的问题")})
        refiner = AERefiner(flowOutput=refiner_output)
        self.addFlow(refiner)

    def role_brief(self) -> str:
        """覆写：Chat 不向 LLM 声明身份与能力，返回空字符串。"""
        return ""

    def startFlow(self, flowInput: AEFlowInput) -> None:
        """启动 chat flow：交基类置 input 并切到 processing，随后启动首个子 flow。

        - 仅当基类 startFlow 返回 True（成功启动）时，才取首个子 flow（问题精炼）启动
        """
        if not super().startFlow(flowInput):
            logger.warning("[%s][%s][d=%s] startFlow 失败：基类未启动（非 default 状态），忽略", type(self).__name__, self.title, self.deepth)
            return
        next_flow = self.nextFlow()
        if next_flow is None:
            logger.warning("[%s][%s][d=%s] startFlow 失败：无 default 状态子 flow 可启动", type(self).__name__, self.title, self.deepth)
            return
        next_flow.startFlow(flowInput)


