import logging
from Network.Core import AENetReq, AENetRsp
from Network.Core.AENetRsp import AENetRspCode
from Assistant.AERole import AERole
from .AEBaseContext import AEBaseContext
from .AEContextPath import AE_PATH_CONTEXT_CHAT_LIST
from .AEContextType import AEContextType
from .AELLMPayload import AELLMPayload

logger = logging.getLogger(__name__)


class AEWorkSpaceContext(AEBaseContext):

    def __init__(self, user=None, space: str = ""):
        super().__init__(context_type=AEContextType.workspace, user=user, space=space)

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

        payload = AELLMPayload(
            messages=[{"role": AERole.USER.value, "content": question.content}],
        )

        def on_reply(reply: str):
            if reply:
                response = AENetRsp(
                    code=AENetRspCode.success,
                    rsp={"reply": reply},
                    req=request.req,
                    cont=request.cont,
                    user=request.user
                )
            else:
                response = AENetRsp(
                    code=AENetRspCode.serverError,
                    rsp={"error": "LLM returned empty response"},
                    req=request.req,
                    cont=request.cont,
                    user=request.user
                )
            self.send_response(response)

        await self.send_llm_request(payload, on_reply)

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
