from typing import Dict, Optional, TYPE_CHECKING
from datetime import datetime
import asyncio
import logging

from Network.Core import AENetReq, AENetRsp
from .AEBaseContext import AEBaseContext
from .AEDirectoryContext import AEDirectoryContext
from .AEPermissionContext import AEPermissionContext
from .AEWorkSpaceContext import AEWorkSpaceContext

if TYPE_CHECKING:
    from Network.Socket.IResponseSender import IResponseSender

logger = logging.getLogger(__name__)


class AEContextManager:
    def __init__(self, response_sender: Optional['IResponseSender'] = None):
        self._response_sender = response_sender
        self.contexts: Dict[str, AEBaseContext] = {}
        self._builtin_handlers = [AEDirectoryContext(), AEPermissionContext()]
        for handler in self._builtin_handlers:
            handler.set_delegate(self)
        logger.info("AEContextManager initialized")

    def handle_request(self, request: AENetReq, connection_id: str) -> None:
        try:
            path = request.path
            if path == "/ae/context/create":
                self._handle_create(request, connection_id)
            elif path == "/ae/context/chat":
                self._handle_chat(request, connection_id)
            else:
                context = self._find_context_for_path(path)
                if not context:
                    raise ValueError(f"No context matches path: {path}")
                self._run_context(context, request, connection_id)
        except Exception as e:
            logger.error(f"Error handling request: {e}", exc_info=True)
            response = AENetRsp.create_error(requestId=request.requestId, error_code="ERR_INTERNAL", error_message=str(e))
            self.send_response(connection_id, response)

    def _handle_create(self, request: AENetReq, connection_id: str) -> None:
        import uuid
        ident = str(uuid.uuid4())
        context_info = request.context.copy() if request.context else {}
        context_info["ident"] = ident
        context = AEWorkSpaceContext(context_info)
        context.set_delegate(self)
        self.contexts[ident] = context

        response = AENetRsp.create_success(requestId=request.requestId, result={"context_info": context.context_info})
        self.send_response(connection_id, response)

    def _handle_chat(self, request: AENetReq, connection_id: str) -> None:
        ident = self._get_ident(request)
        if not ident:
            raise ValueError("Missing context.ident in request")

        context = self.contexts.get(ident)
        if not context:
            raise ValueError(f"Context not found: {ident}")

        self._run_context(context, request, connection_id)

    def _find_context_for_path(self, path: Optional[str]) -> Optional[AEBaseContext]:
        if not path:
            return None
        for handler in self._builtin_handlers:
            if handler.matches_path(path):
                return handler
        for context in self.contexts.values():
            if context.matches_path(path):
                return context
        return None

    def _get_ident(self, request: AENetReq) -> Optional[str]:
        if not request.context or not isinstance(request.context, dict):
            return None
        return request.context.get("ident")

    def _run_context(self, context: AEBaseContext, request: AENetReq, connection_id: str) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(context.handle_request(request, connection_id))
        finally:
            loop.close()

    def register_context(self, context: AEBaseContext) -> None:
        context.set_delegate(self)
        self.contexts[context.ident] = context

    def unregister_context(self, ident: str) -> None:
        self.contexts.pop(ident, None)

    def send_response(self, connection_id: str, response: AENetRsp) -> None:
        if self._response_sender:
            self._response_sender.send_response(connection_id, response)
