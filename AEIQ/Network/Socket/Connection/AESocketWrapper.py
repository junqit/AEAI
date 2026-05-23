import socket
import threading
import logging
from typing import Optional, List
from ...Core import AENetReq, AENetRsp
from .AESocketListener import AESocketListener
from ..Packet.AEPacket import AEPacket, AEDataType
from ..Packet.AEPacketParser import AEPacketParser

logger = logging.getLogger(__name__)


class AESocketWrapper:
    """
    Socket 包装类

    功能：
    1. 封装原始 socket 连接
    2. 提供发送数据的能力（使用 AENetReq 包装）
    3. 在独立线程中接收数据（使用 AENetRsp 包装）
    4. 支持注册监听器来处理接收到的数据
    """

    def __init__(self, sock: socket.socket, addr: Optional[tuple] = None, buffer_size: int = 10 * 1024 * 1024, is_udp: bool = False):
        self._socket = sock
        self._addr = addr
        self._is_udp = is_udp
        self._listeners: List[AESocketListener] = []
        self._receive_thread: Optional[threading.Thread] = None
        self._running = False
        self._lock = threading.Lock()

        self._parser = AEPacketParser(
            on_request_callback=self._on_request_parsed,
            on_response_callback=self._on_response_parsed,
            on_error_callback=self._on_parser_error,
            buffer_size=buffer_size
        )

        logger.info(f"Socket wrapper created for {addr}, UDP mode: {is_udp}")

    def add_listener(self, listener: AESocketListener) -> None:
        with self._lock:
            if listener not in self._listeners:
                self._listeners.append(listener)
                logger.debug(f"Listener added: {listener.__class__.__name__}")

    def remove_listener(self, listener: AESocketListener) -> None:
        with self._lock:
            if listener in self._listeners:
                self._listeners.remove(listener)
                logger.debug(f"Listener removed: {listener.__class__.__name__}")

    def start_receiving(self) -> None:
        if self._running:
            logger.warning("Receive thread is already running")
            return

        self._running = True

        self._parser.start()

        if not self._is_udp:
            self._receive_thread = threading.Thread(
                target=self._receive_loop,
                daemon=True,
                name=f"SocketReceiver-{self._addr}"
            )
            self._receive_thread.start()
            logger.info(f"Started receiving for {self._addr}")
        else:
            logger.info(f"UDP mode: parser started for {self._addr}, waiting for data feed")

    def _receive_loop(self) -> None:
        try:
            while self._running:
                try:
                    chunk = self._socket.recv(8192)
                    if not chunk:
                        logger.info(f"Connection closed by peer: {self._addr}")
                        break

                    self._parser.feed(chunk)

                    logger.debug(f"Received {len(chunk)} bytes")

                except socket.timeout:
                    continue
                except Exception as e:
                    logger.error(f"Error receiving data: {e}")
                    self._notify_error(e)
                    break

        except Exception as e:
            logger.error(f"Error in receive loop: {e}")
            self._notify_error(e)

        finally:
            self._running = False
            self._notify_connection_closed()
            logger.info("Receive loop ended")

    def _on_request_parsed(self, request: AENetReq) -> None:
        self._notify_listeners_request(request)

    def _on_response_parsed(self, response: AENetRsp) -> None:
        self._notify_listeners(response)

    def _on_parser_error(self, error: Exception) -> None:
        self._notify_error(error)

    def feed_data(self, data: bytes) -> None:
        self._parser.feed(data)
        logger.debug(f"Fed {len(data)} bytes to parser")

    def _recv_exact(self, num_bytes: int) -> Optional[bytes]:
        data = bytearray()
        while len(data) < num_bytes:
            try:
                chunk = self._socket.recv(num_bytes - len(data))
                if not chunk:
                    return None
                data.extend(chunk)
            except socket.timeout:
                continue
            except Exception as e:
                logger.error(f"Error receiving data: {e}")
                return None
        return bytes(data)

    def send(self, request: AENetReq, data_type: AEDataType = AEDataType.REQUEST) -> bool:
        try:
            data = request.model_dump_json().encode('utf-8')
            packet = AEPacket.create(data_type, data)
            self._socket.sendall(packet.to_bytes())
            logger.debug(f"Sent request: type={data_type.name}, size={len(data)} bytes")
            return True
        except Exception as e:
            logger.error(f"Failed to send request: {e}")
            self._notify_error(e)
            return False

    def send_response(self, response: AENetRsp) -> bool:
        try:
            data = response.model_dump_json().encode('utf-8')
            packet = AEPacket.create(AEDataType.RESPONSE, data)

            if self._is_udp:
                self._socket.sendto(packet.to_bytes(), self._addr)
            else:
                self._socket.sendall(packet.to_bytes())

            logger.debug(f"Sent response: size={len(data)} bytes, UDP={self._is_udp}")
            return True
        except Exception as e:
            logger.error(f"Failed to send response: {e}")
            self._notify_error(e)
            return False

    def send_heartbeat(self) -> bool:
        try:
            packet = AEPacket.create(AEDataType.HEARTBEAT, b'')
            self._socket.sendall(packet.to_bytes())
            logger.debug("Sent HEARTBEAT")
            return True
        except Exception as e:
            logger.error(f"Failed to send heartbeat: {e}")
            return False

    def send_ping(self) -> bool:
        try:
            packet = AEPacket.create(AEDataType.PING, b'')
            self._socket.sendall(packet.to_bytes())
            logger.debug("Sent PING")
            return True
        except Exception as e:
            logger.error(f"Failed to send ping: {e}")
            return False

    def _send_pong(self) -> bool:
        try:
            packet = AEPacket.create(AEDataType.PONG, b'')
            self._socket.sendall(packet.to_bytes())
            logger.debug("Sent PONG")
            return True
        except Exception as e:
            logger.error(f"Failed to send pong: {e}")
            return False

    def _handle_heartbeat(self) -> None:
        pass

    def _notify_listeners(self, response: AENetRsp) -> None:
        with self._lock:
            listeners = self._listeners.copy()

        for listener in listeners:
            try:
                listener.on_data_received(response)
            except Exception as e:
                logger.error(f"Error in listener {listener.__class__.__name__}: {e}")

    def _notify_listeners_request(self, request: AENetReq) -> None:
        with self._lock:
            listeners = self._listeners.copy()

        for listener in listeners:
            try:
                if hasattr(listener, 'on_request_received'):
                    listener.on_request_received(request)
                else:
                    logger.debug(f"Listener {listener.__class__.__name__} doesn't have on_request_received, skipping")
            except Exception as e:
                logger.error(f"Error in listener {listener.__class__.__name__}: {e}")

    def _notify_connection_closed(self) -> None:
        with self._lock:
            listeners = self._listeners.copy()

        for listener in listeners:
            try:
                listener.on_connection_closed()
            except Exception as e:
                logger.error(f"Error in listener {listener.__class__.__name__}: {e}")

    def _notify_error(self, error: Exception) -> None:
        with self._lock:
            listeners = self._listeners.copy()

        for listener in listeners:
            try:
                listener.on_error(error)
            except Exception as e:
                logger.error(f"Error in listener {listener.__class__.__name__}: {e}")

    def stop_receiving(self) -> None:
        self._running = False
        self._parser.stop()

        if self._receive_thread and self._receive_thread.is_alive():
            self._receive_thread.join(timeout=2.0)

    def close(self) -> None:
        logger.info(f"Closing socket connection: {self._addr}")
        self.stop_receiving()

        try:
            self._socket.close()
        except Exception as e:
            logger.error(f"Error closing socket: {e}")

    @property
    def is_connected(self) -> bool:
        return self._running and self._socket.fileno() != -1

    @property
    def is_udp(self) -> bool:
        return self._is_udp

    @property
    def address(self) -> Optional[tuple]:
        return self._addr

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
