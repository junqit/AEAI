import uuid
import logging
from typing import Optional, TYPE_CHECKING

from Network.Core import AENetReq, AENetRsp
from Network.Core.AENetReq import AENetReqContext
from Network.Core.AENetRsp import AENetRspCode

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .AEContextDelegate import AEContextDelegate


class AEBaseContext:

    def __init__(self):
        self.ident: str = str(uuid.uuid4())
        self.delegate: Optional['AEContextDelegate'] = None

    def set_delegate(self, delegate: 'AEContextDelegate') -> None:
        self.delegate = delegate

    def send_request(self, request: AENetReq) -> None:
        if not self.delegate:
            raise ValueError("Context delegate is not set")
        self.delegate.send_request(request)

    def send_response(self, response: AENetRsp) -> None:
        logger.info(f"[BaseContext] send_response: delegate={'set' if self.delegate else 'None'}")
        if not self.delegate:
            raise ValueError("Context delegate is not set")
        self.delegate.send_response(response)

    async def handle_request(self, request: AENetReq) -> None:
        path = request.req.path if request.req else None

        if path == "/ae/context/create":
            self._handle_create(request)
            return

        await self.on_request(request)

    def _handle_create(self, request: AENetReq) -> None:
        """返回当前 Context 基础信息"""
        response = AENetRsp(
            code=AENetRspCode.success,
            cont=AENetReqContext(
                type=request.cont.type if request.cont else None,
                ident=self.ident
            ),
            req=request.req,
            user=request.user
        )
        self.send_response(response)

    async def on_request(self, request: AENetReq) -> None:
        """子类重写此方法处理具体业务请求"""
        pass
