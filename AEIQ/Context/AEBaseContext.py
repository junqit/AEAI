import uuid
import logging
from typing import Dict, Optional, TYPE_CHECKING

from Network.Core import AENetReq, AENetRsp
from Network.Core.AENetReq import AENetReqContext
from Network.Core.AENetRsp import AENetRspCode
from .AEContextPath import AE_PATH_CONTEXT_CREATE
from .AEContextType import AEContextType

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .AEContextDelegate import AEContextDelegate


class AEBaseContext:

    def __init__(self, context_type: AEContextType, space: str = ""):
        self.ident: str = str(uuid.uuid4())
        self.space: str = space
        self.context_type: AEContextType = context_type
        self.delegate: Optional['AEContextDelegate'] = None

    def context_config(self) -> Dict[str, str]:
        return {
            "ident": self.ident,
            "space": self.space,
            "type": self.context_type.value,
        }

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

        if path == AE_PATH_CONTEXT_CREATE:
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
