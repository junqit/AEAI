"""
Socket 服务器

提供 UDP Socket 服务
数据流: AEPacketReceiveBuffer → AESocketServer → AESocketManager → AESocketListener → 上层业务
"""

import socket
import threading
import logging
from typing import Optional

from ..Packet.AEPacketReceiveBuffer import AEPacketReceiveBuffer, ParsedPacketResult
from ..Packet.AEPacket import AEPacket, AEDataType
from ...Core import AENetReq, AENetRsp
from .AESocketManager import AESocketManager
from .AESocketListener import AESocketListener, AESocketInterface

logger = logging.getLogger(__name__)


class AESocketServer:
    """
    UDP Socket 服务器

    功能：
    1. 监听 UDP 端口，接收数据交给 AEPacketReceiveBuffer
    2. AEPacketReceiveBuffer 解析完成后回调本类
    3. 本类转发给 AESocketManager 处理
    4. AESocketManager 通过 AESocketListener 通知上层业务
    5. 发送能力委托给 AESocketManager
    """

    def __init__(self, host: str = '0.0.0.0', port: int = 8888):
        self.host = host
        self.port = port
        self.server_socket: Optional[socket.socket] = None
        self.receive_thread: Optional[threading.Thread] = None
        self.running = False

        self._socket_manager = AESocketManager()
        self._receive_buffer = AEPacketReceiveBuffer(
            on_packet_received=self._on_packet_received
        )

        logger.info(f"UDP Socket server initialized on {host}:{port}")

    @property
    def socket_manager(self) -> AESocketManager:
        return self._socket_manager

    def add_listener(self, listener: AESocketListener) -> None:
        self._socket_manager.add_listener(listener)

    def remove_listener(self, listener: AESocketListener) -> None:
        self._socket_manager.remove_listener(listener)

    def start(self) -> None:
        if self.running:
            logger.warning("Server is already running")
            return

        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.host, self.port))

            self.running = True

            self._socket_manager.set_socket(self.server_socket)
            self._receive_buffer.start()

            self.receive_thread = threading.Thread(
                target=self._receive_loop,
                daemon=True,
                name="UDPSocketServerReceive"
            )
            self.receive_thread.start()

            logger.info(f"UDP Socket server started on {self.host}:{self.port}")

        except Exception as e:
            logger.error(f"Failed to start server: {e}")
            raise

    def stop(self) -> None:
        logger.info("Stopping UDP socket server")
        self.running = False

        self._receive_buffer.stop()

        if self.server_socket:
            try:
                self.server_socket.close()
            except Exception as e:
                logger.error(f"Error closing server socket: {e}")

        if self.receive_thread and self.receive_thread.is_alive():
            self.receive_thread.join(timeout=2.0)

        logger.info("UDP Socket server stopped")

    def _receive_loop(self) -> None:
        logger.info("UDP receive loop started")

        while self.running:
            try:
                data, client_addr = self.server_socket.recvfrom(65535)
                self._receive_buffer.receive(data, client_addr)

            except OSError as e:
                if self.running:
                    logger.error(f"Error receiving data: {e}")
                break
            except Exception as e:
                logger.error(f"Unexpected error in receive loop: {e}")
                if not self.running:
                    break

        logger.info("UDP receive loop ended")

    def _on_packet_received(self, result: ParsedPacketResult) -> None:
        """AEPacketReceiveBuffer 解析完成后的回调，转给 AESocketManager"""
        self._socket_manager.on_packet_received(result)

    def send_request(self, request: AENetReq) -> bool:
        """AESocketInterface: 委托给 AESocketManager"""
        return self._socket_manager.send_request(request)

    def send_response(self, response: AENetRsp) -> bool:
        """AESocketInterface: 委托给 AESocketManager"""
        return self._socket_manager.send_response(response)

    @property
    def is_running(self) -> bool:
        return self.running


# 全局服务器实例
_server_instance: Optional[AESocketServer] = None


def get_socket_server(host: str = '0.0.0.0', port: int = 8888) -> AESocketServer:
    global _server_instance

    if _server_instance is None:
        _server_instance = AESocketServer(host, port)

    return _server_instance


def start_socket_server(host: str = '0.0.0.0', port: int = 8888) -> AESocketServer:
    server = get_socket_server(host, port)
    if not server.is_running:
        server.start()
    return server


def stop_socket_server() -> None:
    global _server_instance

    if _server_instance:
        _server_instance.stop()
