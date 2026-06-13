import os
import platform
import logging
from Network.Core import AENetReq, AENetRsp
from Network.Core.AENetRsp import AENetRspCode
from .AEBaseContext import AEBaseContext
from .AEContextPath import AE_PATH_CONTEXT_INFO
from .AEContextType import AEContextType

logger = logging.getLogger(__name__)

class AEDirectoryContext(AEBaseContext):

    def __init__(self, user=None, space: str = ""):
        super().__init__(context_type=AEContextType.directory, user=user, space=space)

    async def on_request(self, request: AENetReq) -> None:
        path = request.req.path if request.req else None

        if path == AE_PATH_CONTEXT_INFO:
            self._handle_info(request)
            return

        logger.info(f"AEDirectoryContext on_request: {request.model_dump_json(exclude_none=True)}")

    def _handle_info(self, request: AENetReq) -> None:
        cwd = os.getcwd()
        info = {
            "system": platform.system(),
            "node": platform.node(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "cwd": cwd,
        }
        response = AENetRsp(
            code=AENetRspCode.success,
            rsp=info,
            req=request.req,
            cont=request.cont,
            user=request.user
        )
        self.send_response(response)
