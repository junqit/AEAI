import json
import uuid
import asyncio
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
        question = request.cont.ques if request.cont else None
        
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
        self._chat_map[chat.ident] = chat
        logger.info(f"AEChat created and stored - chat_ident={chat.ident}, space={self.space}")

        # receiveQuestion 内含同步阻塞的 LLM 往返，丢到线程池异步处理，避免阻塞 _loop
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, chat.receiveQuestion, question)

    # ==================== AEFlowDelegate 实现 ====================

    def flow_llm(self, payload: "AELLMPayload") -> None:
        """AEFlowDelegate: 转发 flow 的 LLM 请求，经本 Context 的 send_llm_request 上送；
        用 context.ident 包装 out_schema，回程按 ident 路由回本 Context"""
        # 用当前 Context 的 ident 包装 out_schema
        payload.out_schema = {"ident": self.ident, "llm_out": payload.out_schema}
        self.send_llm_request(payload)

    def next_flow_input_schema(self, info: "Optional[AEFlowInfo]" = None) -> "Optional[AEFlowInfo]":
        """AEFlowDelegate: Context 非 flow 容器，不持有子 flow 序列，返回 None"""
        return None

    def flow_complete(self, result, flowStatus) -> None:
        """AEFlowDelegate: flow 完成通知，记录日志"""
        flow_ident = result.get("ident") if isinstance(result, dict) else None
        logger.info(f"WorkSpaceContext {self.ident} 收到 flow_complete - flow_ident={flow_ident}, status={flowStatus}")

    def receive_llm_response(self, data: dict) -> None:
        """
        处理 LLM 回复（已被 AEUserContext 按第一层 ident 路由到本 Context）：

        - 判断第一层 ident 是否为本 Context 的 ident
        - 取内层 out_schema（含 chat.ident + 实际 schema）
        - 按 out_schema.ident 从 _chat_map 取到 AEChat
        - 通过 AEChat.receiveInputSchemaData 再次取 out_schema 向下传递
        """
        if not isinstance(data, dict):
            logger.error(f"[WorkSpace:{self.ident}] LLM 回复非 map: {data!r}")
            return
        # 打印 LLM 回复的 JSON 结构性数据
        logger.info(
            "[WorkSpace:%s] 收到 LLM 回复:\n%s",
            self.ident,
            json.dumps(data, ensure_ascii=False, indent=2),
        )
        ident = data.get("ident")
        if ident != self.ident:
            logger.error(f"[WorkSpace:{self.ident}] 第一层 ident={ident!r} 非本 Context，忽略")
            return
        out_schema = data.get("llm_out")
        if not isinstance(out_schema, dict):
            logger.error(f"[WorkSpace:{self.ident}] 内层 out_schema 非 map: {out_schema!r}")
            return
        chat_ident = out_schema.get("ident")
        chat = self._chat_map.get(chat_ident)
        if chat is None:
            logger.error(f"[WorkSpace:{self.ident}] _chat_map 内未找到 chat_ident={chat_ident!r}")
            return
        # 再获取一层 out_schema（剥掉 chat.ident 层），传给 AEChat 继续路由到子 flow
        out_schema = out_schema.get("llm_out")
        if not isinstance(out_schema, dict):
            logger.error(f"[WorkSpace:{self.ident}] chat 内层 out_schema 非 map: {out_schema!r}")
            return
        chat.receiveInputSchemaData(out_schema)

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
