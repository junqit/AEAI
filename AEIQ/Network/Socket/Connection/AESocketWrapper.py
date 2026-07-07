import socket
import logging
from typing import Optional

from ...Core.AENetReq import AENetReq, AEUserInfo
from ...Core.AENetRsp import AENetRsp
from ..Packet.AEPacket import AEPacket, AEDataType

logger = logging.getLogger(__name__)


class AESocketWrapper:
    """
    用户 Socket 包装

    记录用户信息与最后一次收到数据的 addr，负责发送数据
    """

    def __init__(self, user: AEUserInfo, client_addr: tuple, server_socket: socket.socket):
        self._user = user
        self._client_addr = client_addr
        self._server_socket = server_socket
        logger.debug(f"AESocketWrapper created: user={user.user_key}, addr={client_addr}")

    @property
    def user(self) -> AEUserInfo:
        return self._user

    @property
    def client_addr(self) -> tuple:
        return self._client_addr

    def update_addr(self, client_addr: tuple) -> None:
        if self._client_addr != client_addr:
            logger.debug(f"Address updated: user={self._user.user_key}, {self._client_addr} -> {client_addr}")
            self._client_addr = client_addr

    def _send_data(self, data_type: AEDataType, data: bytes) -> None:
        """由 AEPacket.packets_from_data 生成 packet 列表，循环 sendto 发送。"""
        packets = AEPacket.packets_from_data(data_type, data)
        if len(packets) > 1:
            logger.info(
                "send %s 分片 - data_size=%d, fragments=%d",
                self._client_addr, len(data), len(packets),
            )
        for packet in packets:
            self._server_socket.sendto(packet.to_bytes(), self._client_addr)

    def send_request(self, request: AENetReq) -> bool:
        try:
            data = request.to_bytes()
            self._send_data(AEDataType.REQUEST, data)
            return True
        except Exception as e:
            logger.error(f"Failed to send request to {self._client_addr}: {e}")
            return False

    def send_response(self, response: AENetRsp) -> bool:
        try:
            data = response.to_bytes()
            logger.info(
                "send_response to %s - data_size=%d bytes",
                self._client_addr, len(data),
            )
            self._send_data(AEDataType.RESPONSE, data)
            return True
        except Exception as e:
            logger.error(f"Failed to send response to {self._client_addr}: {e}")
            return False
