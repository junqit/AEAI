"""
Socket 连接管理器

存储每个用户对应的 AESocketWrapper，
接收解析完成的数据后通过 AESocketListener 转给上层业务，
发送数据时委托给对应用户的 AESocketWrapper 处理
"""

import socket
import threading
import logging
from typing import Dict, Optional, List

from ...Core.AENetReq import AENetReq, AEUserInfo
from ...Core.AENetRsp import AENetRsp
from ..Packet.AEPacketReceiveBuffer import ParsedPacketResult
from ..Packet.AEPacket import AEDataType
from .AESocketWrapper import AESocketWrapper
from .AESocketListener import AESocketListener

logger = logging.getLogger(__name__)


class AESocketManager:
    """
    Socket 连接管理器

    职责：
    1. 接收解析完成的数据
    2. 为每个用户创建/更新 AESocketWrapper
    3. 通过 AESocketListener 通知上层业务
    4. 发送数据委托给用户对应的 AESocketWrapper
    """

    def __init__(self):
        self._server_socket: Optional[socket.socket] = None
        self._wrappers: Dict[str, AESocketWrapper] = {}
        self._lock = threading.Lock()
        self._listeners: List[AESocketListener] = []
        logger.info("AESocketManager initialized")

    def set_socket(self, server_socket: socket.socket) -> None:
        self._server_socket = server_socket

    def add_listener(self, listener: AESocketListener) -> None:
        self._listeners.append(listener)

    def remove_listener(self, listener: AESocketListener) -> None:
        self._listeners.remove(listener)

    def on_packet_received(self, result: ParsedPacketResult) -> None:
        """接收解析完成的数据，注册用户后通过 listener 转给上层"""

        if result.data_type == AEDataType.REQUEST:
            request: AENetReq = result.payload
            if request.user:
                self._register_user(request.user, result.client_addr)
                
            for listener in self._listeners:
                listener.on_request_received(request)
        elif result.data_type == AEDataType.PING:
            logger.debug(f"PING from {result.client_addr}")
        elif result.data_type == AEDataType.HEARTBEAT:
            logger.debug(f"Heartbeat from {result.client_addr}")

    def send_request(self, request: AENetReq) -> bool:
        """发送 AENetReq，委托给用户对应的 AESocketWrapper"""
        if not request.user:
            logger.error("Cannot send request: no user info")
            return False

        wrapper = self._get_wrapper(request.user)
        if not wrapper:
            logger.error(f"Cannot send request: no wrapper for user {request.user.user_key}")
            return False

        return wrapper.send_request(request)

    def send_response(self, response: AENetRsp) -> bool:
        """发送 AENetRsp，委托给用户对应的 AESocketWrapper"""
        if not response.user:
            logger.error("Cannot send response: no user info")
            return False

        wrapper = self._get_wrapper(response.user)
        if not wrapper:
            logger.error(f"Cannot send response: no wrapper for user {response.user.user_key}")
            return False

        return wrapper.send_response(response)

    def _get_wrapper(self, user: AEUserInfo) -> Optional[AESocketWrapper]:
        key = self._user_key(user)
        with self._lock:
            return self._wrappers.get(key)

    def _register_user(self, user: AEUserInfo, client_addr: tuple) -> None:
        key = self._user_key(user)
        with self._lock:
            wrapper = self._wrappers.get(key)
            if wrapper:
                wrapper.update_addr(client_addr)
            else:
                wrapper = AESocketWrapper(user, client_addr, self._server_socket)
                self._wrappers[key] = wrapper
                logger.debug(f"User wrapper created: {key} -> {client_addr}")

    def _user_key(self, user: AEUserInfo) -> str:
        return user.user_key

    def __len__(self) -> int:
        with self._lock:
            return len(self._wrappers)
