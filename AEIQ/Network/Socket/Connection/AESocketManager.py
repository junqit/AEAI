"""
Socket 连接管理器

接收 AESocketServer 转发的解析数据，
以 AENetReqUser 为 key 存储用户发送数据时的 addr，
处理完后通过 AESocketListener 转给上层业务
"""

import threading
import logging
from typing import Dict, Optional, List

from ...Core.AENetReq import AENetReq, AENetReqUser
from ..Packet.AEPacketReceiveBuffer import ParsedPacketResult
from ..Packet.AEPacket import AEDataType
from .AESocketListener import AESocketListener

logger = logging.getLogger(__name__)


class AESocketManager:
    """
    Socket 连接管理器

    职责：
    1. 接收解析完成的数据
    2. 以 AENetReqUser 为 key 存储 client_addr
    3. 通过 AESocketListener 通知上层业务
    """

    def __init__(self):
        self._user_addrs: Dict[str, tuple] = {}
        self._lock = threading.Lock()
        self._listeners: List[AESocketListener] = []
        logger.info("AESocketManager initialized")

    def add_listener(self, listener: AESocketListener) -> None:
        self._listeners.append(listener)

    def remove_listener(self, listener: AESocketListener) -> None:
        self._listeners.remove(listener)

    def on_packet_received(self, result: ParsedPacketResult) -> None:
        """接收解析完成的数据，处理后通过 listener 转给上层"""
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

    def get_addr_by_user(self, user: AENetReqUser) -> Optional[tuple]:
        key = self._user_key(user)
        with self._lock:
            return self._user_addrs.get(key)

    def remove_user(self, user: AENetReqUser) -> None:
        key = self._user_key(user)
        with self._lock:
            self._user_addrs.pop(key, None)

    def _register_user(self, user: AENetReqUser, client_addr: tuple) -> None:
        key = self._user_key(user)
        with self._lock:
            self._user_addrs[key] = client_addr
        logger.debug(f"User registered: {key} -> {client_addr}")

    def _user_key(self, user: AENetReqUser) -> str:
        return f"{user.uid}:{user.ident}"

    def __len__(self) -> int:
        with self._lock:
            return len(self._user_addrs)
