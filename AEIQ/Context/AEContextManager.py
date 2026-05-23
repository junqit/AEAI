from typing import Dict, Optional, TYPE_CHECKING
import asyncio
import logging

from Network.Core import AENetReq
from .AEBaseContext import AEBaseContext
from .AEContextType import AEContextType
from .AEDirectoryContext import AEDirectoryContext
from .AEPermissionContext import AEPermissionContext
from .AEWorkSpaceContext import AEWorkSpaceContext

if TYPE_CHECKING:
    from Network.Socket.Connection.AESocketServer import AESocketServer

logger = logging.getLogger(__name__)


class AEContextManager:
    """
    接收 NetReq 后通过 user 区分用户，获取对应的 Context 实例处理请求。
    Context 通过 AEContextDelegate.send_request 把需要发送的 NetReq 传回本类。
    """

    def __init__(self, response_sender: Optional['AESocketServer'] = None):
        self._response_sender = response_sender
        # user_key -> { context_ident -> AEBaseContext }
        self._user_contexts: Dict[str, Dict[str, AEBaseContext]] = {}
        logger.info("AEContextManager initialized")

    def on_request_received(self, request: AENetReq) -> None:
        """AESocketListener 接口实现"""
        logger.info(f"NetReq received: {request.model_dump_json(exclude_none=True)}")

        if not request.user:
            logger.warning("Request has no user info, ignored")
            return

        if not request.cont or not request.cont.type:
            logger.warning("Request has no context info, ignored")
            return

        user_key = f"{request.user.uid}:{request.user.ident}"
        context_ident = request.cont.ident if request.cont.ident else request.cont.type

        context = self._get_context(user_key, context_ident)
        if context is None:
            context = self._create_context(user_key, context_ident)

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(context.handle_request(request))
        finally:
            loop.close()

    def send_request(self, request: AENetReq) -> None:
        """AEContextDelegate 接口实现：Context 把需要发送的 NetReq 传回这里"""
        if self._response_sender:
            self._response_sender.send_to(request)

    def _get_context(self, user_key: str, context_ident: str) -> Optional[AEBaseContext]:
        user_map = self._user_contexts.get(user_key)
        if user_map is None:
            return None
        return user_map.get(context_ident)

    def _create_context(self, user_key: str, context_ident: str) -> AEBaseContext:
        try:
            context_type = AEContextType(context_ident)
        except ValueError:
            logger.warning(f"Unknown context ident: {context_ident}")
            return None

        context_map = {
            AEContextType.permission: AEPermissionContext,
            AEContextType.directory: AEDirectoryContext,
            AEContextType.workspace: AEWorkSpaceContext,
        }

        context = context_map[context_type]()

        context.set_delegate(self)

        if user_key not in self._user_contexts:
            self._user_contexts[user_key] = {}

        self._user_contexts[user_key][context_ident] = context
        logger.info(f"Context created: user={user_key}, ident={context_ident}")
        return context
