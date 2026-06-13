import uuid
import hashlib
import logging
from typing import Dict, Optional, TYPE_CHECKING

from Network.Core import AENetReq, AENetRsp
from Network.Core.AENetReq import AENetReqContext, AENetReqUser
from Network.Core.AENetRsp import AENetRspCode
from .AEContextPath import AE_PATH_CONTEXT_CREATE, AE_PATH_CONTEXT_CHAT
from .AEContextType import AEContextType

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .AEContextDelegate import AEContextDelegate


class AEBaseContext:

    def __init__(self, context_type: AEContextType, user: AENetReqUser = None, space: str = ""):
        self.user: Optional[AENetReqUser] = user
        self.ident: str = self._generate_ident(context_type, user, space)
        self.space: str = space
        self.context_type: AEContextType = context_type
        self.delegate: Optional['AEContextDelegate'] = None

    @staticmethod
    def _generate_ident(context_type: AEContextType, user: Optional[AENetReqUser], space: str = "") -> str:
        user_info = user.user_key if user else ""

        if context_type == AEContextType.workspace:
            raw = f"{user_info}{space}"
            return hashlib.md5(raw.encode()).hexdigest()

        if context_type == AEContextType.directory:
            raw = f"{user_info}directory"
            return hashlib.md5(raw.encode()).hexdigest()

        if context_type == AEContextType.permission:
            raw = f"{user_info}permission"
            return hashlib.md5(raw.encode()).hexdigest()

        return uuid.uuid4().hex

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
        if not self.delegate:
            raise ValueError("Context delegate is not set")
        self.delegate.send_response(response)

    async def send_llm_request(self, payload, callback) -> None:
        if not self.delegate:
            raise ValueError("Context delegate is not set")
        await self.delegate.send_llm_request(payload, callback)

    async def handle_request(self, request: AENetReq) -> None:
        path = request.req.path if request.req else None

        if path == AE_PATH_CONTEXT_CREATE:
            self._handle_create(request)
            return

        if path == AE_PATH_CONTEXT_CHAT:
            await self.on_chat(request)
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

    async def on_chat(self, request: AENetReq) -> None:
        """子类重写此方法处理 Chat 消息"""
        pass

    async def on_request(self, request: AENetReq) -> None:
        """子类重写此方法处理具体业务请求"""
        pass
