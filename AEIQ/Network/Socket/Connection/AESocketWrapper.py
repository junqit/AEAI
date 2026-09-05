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

    @property
    def user(self) -> AEUserInfo:
        return self._user

    @property
    def client_addr(self) -> tuple:
        return self._client_addr

    def update_addr(self, client_addr: tuple) -> None:
        if self._client_addr != client_addr:
            self._client_addr = client_addr

    def _send_data(self, data_type: AEDataType, data: bytes) -> None:
        """由 AEPacket.packets_from_data 生成 packet 列表，循环 sendto 发送。"""
        packets = AEPacket.packets_from_data(data_type, data)
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
            # 诊断：打印实际发到网络上的响应字节前 300 字符（reply 在 JSON 首部，可据此确认服务端究竟发了什么）
            logger.info("[AESocketWrapper] send_response req=%s len=%d head=%s",
                        response.req, len(data), data[:300].decode('utf-8', 'replace'))
            self._send_data(AEDataType.RESPONSE, data)
            return True
        except Exception as e:
            logger.error(f"Failed to send response to {self._client_addr}: {e}")
            return False
