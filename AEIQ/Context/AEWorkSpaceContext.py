import logging
import httpx
from Network.Core import AENetReq, AENetRsp
from Network.Core.AENetRsp import AENetRspCode, AENetRspResult
from .AEBaseContext import AEBaseContext
from .AEContextPath import AE_PATH_CONTEXT_CHAT_LIST
from .AEContextType import AEContextType

logger = logging.getLogger(__name__)

LLM_SERVICE_URL = "http://127.0.0.1:9999/aellms/question"
LLM_API_KEY = "ae-agent-2024-fixed-key-9527"


class AEWorkSpaceContext(AEBaseContext):

    def __init__(self, space: str = ""):
        super().__init__(context_type=AEContextType.workspace, space=space)

    async def on_chat(self, request: AENetReq) -> None:
        question = request.question
        if not question or not question.content:
            response = AENetRsp(
                code=AENetRspCode.badRequest,
                rsp=AENetRspResult(data={"error": "missing question content"}),
                req=request.req,
                cont=request.cont,
                user=request.user
            )
            self.send_response(response)
            return

        try:
            payload = {
                "messages": [{"role": "user", "content": question.content}],
                "llm_type": "GEMINI",
                "level": "default",
            }
            headers = {"AE-API-Key": LLM_API_KEY}

            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(LLM_SERVICE_URL, json=payload, headers=headers)
                result = resp.json()

            reply = result.get("response", "")
            response = AENetRsp(
                code=AENetRspCode.success,
                rsp=AENetRspResult(data={"reply": reply}),
                req=request.req,
                cont=request.cont,
                user=request.user
            )
        except Exception as e:
            logger.error(f"LLM service call failed: {e}")
            response = AENetRsp(
                code=AENetRspCode.serverError,
                rsp=AENetRspResult(data={"error": str(e)}),
                req=request.req,
                cont=request.cont,
                user=request.user
            )

        self.send_response(response)

    async def on_request(self, request: AENetReq) -> None:
        path = request.req.path if request.req else None

        if path == AE_PATH_CONTEXT_CHAT_LIST:
            self._handle_chat_list(request)
            return

        logger.info(f"AEWorkSpaceContext on_request: {request.model_dump_json(exclude_none=True)}")

    def _handle_chat_list(self, request: AENetReq) -> None:
        response = AENetRsp(
            code=AENetRspCode.success,
            rsp=AENetRspResult(data={"message": "yellow world"}),
            req=request.req,
            cont=request.cont,
            user=request.user
        )
        self.send_response(response)
