from typing import Dict, List, Optional, TYPE_CHECKING
import asyncio
import logging

from Network.Core import AENetReq, AENetRsp
from Network.Core.AENetRsp import AENetRspCode, AENetRspResult
from Network.Socket.Connection.AESocketListener import AESocketInterface
from .AEBaseContext import AEBaseContext
from .AEContextPath import AE_PATH_CONTEXT_LIST
from .AEContextType import AEContextType
from .AEDirectoryContext import AEDirectoryContext
from .AEPermissionContext import AEPermissionContext
from .AEWorkSpaceContext import AEWorkSpaceContext

logger = logging.getLogger(__name__)


class AEContextManager:
    """
    接收 NetReq 后通过 user 区分用户，获取对应的 Context 实例处理请求。
    Context 通过 AEContextDelegate 把需要发送的数据传回本类，
    本类通过 socketInterface 发送。
    """

    def __init__(self, socket_interface: Optional[AESocketInterface] = None):
        self._socket_interface = socket_interface
        # user_key -> { context_ident -> AEBaseContext }
        self._user_contexts: Dict[str, Dict[str, AEBaseContext]] = {}
        logger.info("AEContextManager initialized")

    def on_request_received(self, request: AENetReq) -> None:
        """AESocketListener 接口实现"""
        logger.info(f"NetReq received: {request.model_dump_json(exclude_none=True)}")

        if not request.user:
            logger.warning("Request has no user info, ignored")
            return

        path = request.req.path if request.req else None
        if path == AE_PATH_CONTEXT_LIST:
            self._handle_context_list(request)
            return

        if not request.cont or not request.cont.type:
            logger.warning("Request has no context info, ignored")
            return

        user_key = f"{request.user.uid}:{request.user.ident}"

        # 先通过 cont.ident 获取已有 context 实例
        context = None
        if request.cont.ident:
            context = self._get_context(user_key, request.cont.ident)

        # 获取不到，通过 cont.type 创建新 context
        if context is None:
            context = self._create_context(user_key, request.cont.type)

        if context is None:
            return

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(context.handle_request(request))
        finally:
            loop.close()

    def send_request(self, request: AENetReq) -> None:
        """AEContextDelegate: Context 需要发送 NetReq 时调用"""
        if self._socket_interface:
            self._socket_interface.send_request(request)

    def send_response(self, response: AENetRsp) -> None:
        """AEContextDelegate: Context 需要发送 NetRsp 时调用"""
        logger.info(f"[ContextManager] send_response called: {response.model_dump_json(exclude_none=True)}")
        logger.info(f"[ContextManager] socket_interface: {'set' if self._socket_interface else 'None'}")
        if self._socket_interface:
            self._socket_interface.send_response(response)

    def _get_context(self, user_key: str, context_ident: str) -> Optional[AEBaseContext]:
        user_map = self._user_contexts.get(user_key)
        if user_map is None:
            return None
        return user_map.get(context_ident)

    def _create_context(self, user_key: str, context_type_str: str) -> Optional[AEBaseContext]:
        try:
            context_type = AEContextType(context_type_str)
        except ValueError:
            logger.warning(f"Unknown context type: {context_type_str}")
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

        self._user_contexts[user_key][context.ident] = context
        logger.info(f"Context created: user={user_key}, ident={context.ident}, type={context_type_str}")
        return context

    def _handle_context_list(self, request: AENetReq) -> None:
        user_key = f"{request.user.uid}:{request.user.ident}"
        user_map = self._user_contexts.get(user_key, {})

        contexts = [context.context_config() for context in user_map.values()]
        logger.info(f"[ContextManager] context_list: user={user_key}, count={len(contexts)}")

        response = AENetRsp(
            code=AENetRspCode.success,
            rsp=AENetRspResult(data={"contexts": contexts}),
            req=request.req,
            user=request.user
        )
        self.send_response(response)
