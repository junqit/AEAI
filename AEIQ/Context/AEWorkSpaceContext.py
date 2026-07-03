import uuid
import logging
from typing import Dict, Optional, TYPE_CHECKING

from Network.Core import AENetReq, AENetRsp
from Network.Core.AENetRsp import AENetRspCode
from Chat.AEChat import AEChat
from .AEBaseContext import AEBaseContext
from .AEContextPath import AE_PATH_CONTEXT_CHAT_LIST
from .AEContextType import AEContextType

if TYPE_CHECKING:
    from WorkFlows.AEFlowInfo import AEFlowInfo
    from .AELLMPayload import AELLMPayload

logger = logging.getLogger(__name__)


class AEWorkSpaceContext(AEBaseContext):

    def __init__(self, user=None, space: str = ""):
        super().__init__(context_type=AEContextType.workspace, user=user, space=space)
        # chat.ident -> AEChat，持有本 workspace 下的会话
        self._chat_map: Dict[str, AEChat] = {}

    async def on_chat(self, request: AENetReq) -> None:
        question = request.question
        if not question or not question.content:
            response = AENetRsp(
                code=AENetRspCode.badRequest,
                rsp={"error": "missing question content"},
                req=request.req,
                cont=request.cont,
                user=request.user
            )
            self.send_response(response)
            return

        # 创建新 AEChat，delegate 设为当前 Context，接收用户信息，按 chat.ident 存入 chat_map
        chat = AEChat(ident=uuid.uuid4().hex)
        chat.set_delegate(self)
        chat.receiveQuestion(question)
        self._chat_map[chat.ident] = chat
        logger.info(f"AEChat created and stored - chat_ident={chat.ident}, space={self.space}")

    # ==================== AEFlowDelegate 实现 ====================

    def flow_llm(self, payload: "AELLMPayload") -> None:
        """AEFlowDelegate: 转发 flow 的 LLM 请求，经本 Context 的 send_llm_request 上送；
        用 context.ident 包装 out_schema，回程按 ident 路由回本 Context"""
        # 用当前 Context 的 ident 包装 out_schema
        payload.out_schema = {"ident": self.ident, "out_schema": payload.out_schema}
        self.send_llm_request(payload)

    def next_flow_input_schema(self, info: "Optional[AEFlowInfo]" = None) -> "Optional[AEFlowInfo]":
        """AEFlowDelegate: Context 非 flow 容器，不持有子 flow 序列，返回 None"""
        return None

    def flow_complete(self, result: "AEFlowInfo") -> None:
        """AEFlowDelegate: flow 完成通知，记录日志"""
        logger.info(f"WorkSpaceContext {self.ident} 收到 flow_complete - flow_ident={getattr(result, 'ident', None)}")

    async def on_request(self, request: AENetReq) -> None:
        path = request.req.path if request.req else None

        if path == AE_PATH_CONTEXT_CHAT_LIST:
            self._handle_chat_list(request)
            return

        logger.info(f"AEWorkSpaceContext on_request: {request.model_dump_json(exclude_none=True)}")

    def _handle_chat_list(self, request: AENetReq) -> None:
        response = AENetRsp(
            code=AENetRspCode.success,
            rsp={"message": "yellow world"},
            req=request.req,
            cont=request.cont,
            user=request.user
        )
        self.send_response(response)
