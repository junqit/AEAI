import uuid
import asyncio
import hashlib
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Optional, TYPE_CHECKING

from Network.Core import AENetReq, AENetRsp
from Network.Core.AENetReq import AENetCont, AENetQues, AENetReqInfo
from Network.Core.AENetRsp import AENetRspCode
from Chat.AEChat import AEChat
from WorkFlows.FlowWork.AEFlowInfo import AE_IDENT, AE_CONTENT
from WorkFlows.FlowWork.AEFlowInput import AEFlowInput, AEFlowStatus, AE_CONTENT
from WorkFlows.FlowWork.AEFlowOutput import AEFlowOutput, AE_LLM_OUT
from .AEContextType import AEContextType

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .AEContextDelegate import AEContextDelegate
    from .AELLMPayload import AELLMPayload


class AEBaseContext:

    def __init__(self, context_type: AEContextType, space: str = ""):
        self.ident: str = self._generate_ident(context_type, space)
        self.space: str = space
        self.context_type: AEContextType = context_type
        self.delegate: Optional['AEContextDelegate'] = None
        self._chat_map: Dict[str, AEChat] = {}
        # 并行队列：独立线程池管理 chat flow 执行，不依赖外部 asyncio 事件循环
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="chat-flow")

    # ==================== 私有方法 ====================

    @staticmethod
    def _generate_ident(context_type: AEContextType, space: str = "") -> str:
        if context_type == AEContextType.workspace:
            return hashlib.md5(space.encode()).hexdigest()
        if context_type == AEContextType.directory:
            return hashlib.md5(b"directory").hexdigest()
        if context_type == AEContextType.permission:
            return hashlib.md5(b"permission").hexdigest()
        return uuid.uuid4().hex

    # ==================== 公开方法 ====================

    def set_delegate(self, delegate: 'AEContextDelegate') -> None:
        self.delegate = delegate

    def context_config(self) -> Dict[str, str]:
        return {AE_IDENT: self.ident, "space": self.space, "type": self.context_type.value}

    def receive_llm_response(self, data: dict) -> None:
        """接收 LLM 回复数据。子类覆写以处理。"""
        pass

    def receive_chat(self, question: AENetQues, req: AENetReqInfo) -> None:
        """创建 AEChat 并提交到并行队列执行。"""
        if question is None:
            logger.error("[Context] 收到的 AENetQues 为空，忽略")
            return
        from .AELLMPayload import llm_generate
        chat_ident = uuid.uuid4().hex
        chat = AEChat(
            ident=chat_ident,
            flowOutput=AEFlowOutput(ident=chat_ident, out_schema={AE_CONTENT: llm_generate("对用户的回复")}),
        )
        chat.req = req
        chat.set_delegate(self)
        self._chat_map[chat.ident] = chat
        logger.info("[Context] receive_chat: %s", question.content or "")
        flow_input = AEFlowInput(content=question.content or "", ident=chat_ident)
        logger.info("[Context] submit chat.receive_flow_input to executor")
        self._executor.submit(chat.receive_flow_input, flow_input)

    # ==================== AEFlowDelegate 协议实现 ====================

    def receive_flow_input(self, flowInput: AEFlowInput) -> bool:
        """收到回复后直接 response——AE_CONTENT 转为 reply 发送响应。"""
        if flowInput.state != AEFlowStatus.complete:
            return False
        chat = self._chat_map.get(flowInput.ident)
        if chat is None:
            logger.warning("[Context] complete 但 _chat_map 未找到 chat(ident=%s)", flowInput.ident)
            return False
        self._chat_map.pop(flowInput.ident, None)
        reply = flowInput.parameter.get(AE_CONTENT, "")
        logger.info("[Context] chat 完成: %s", reply[:100])
        rsp = AENetRsp(
            code=AENetRspCode.success,
            cont=AENetCont(type=self.context_type.value, ident=self.ident, space=self.space),
            req=chat.req,
            rsp={"reply": reply},
        )
        self.send_response(rsp)
        return True

    def add_flow(self, flow) -> None:
        """添加子 flow。"""
        pass

    def flow_send_llm_request(self, payload: "AELLMPayload") -> None:
        """转发 LLM 请求，用 context.ident 包装 out_schema。"""
        payload.out_schema = {AE_IDENT: self.ident, "type": self.context_type.value, AE_LLM_OUT: payload.out_schema}
        logger.info("[Context] flow_send_llm_request -> send_llm_request")
        self.send_llm_request(payload)

    # ==================== delegate 转发 ====================

    def send_request(self, request: AENetReq) -> None:
        if not self.delegate:
            raise ValueError("Context delegate is not set")
        self.delegate.send_request(request)

    def send_response(self, response: AENetRsp) -> None:
        if not self.delegate:
            raise ValueError("Context delegate is not set")
        self.delegate.send_response(response)

    def send_llm_request(self, payload) -> None:
        if not self.delegate:
            raise ValueError("Context delegate is not set")
        logger.info("[Context] send_llm_request -> delegate.send_llm_request")
        self.delegate.send_llm_request(payload)
