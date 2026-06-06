import logging
from Network.Core import AENetReq, AENetRsp
from Network.Core.AENetRsp import AENetRspCode, AENetRspResult
from .AEBaseContext import AEBaseContext
from .AEContextPath import AE_PATH_CONTEXT_CHAT_LIST
from .AEContextType import AEContextType

logger = logging.getLogger(__name__)


class AEWorkSpaceContext(AEBaseContext):

    def __init__(self, space: str = ""):
        super().__init__(context_type=AEContextType.workspace, space=space)

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
