import socket
import threading
import logging
from typing import Optional, List
from ..Core import AENetReq, AENetRsp
from .AESocketListener import AESocketListener
from .AEPacket import AEPacket, AEDataType
from .AEPacketParser import AEPacketParser

logger = logging.getLogger(__name__)


class AESocketWrapper:
    """
    Socket 包装类

    功能：
    1. 封装原始 socket 连接
    2. 提供发送数据的能力（使用 AENetReq 包装）
    3. 在独立线程中接收数据（使用 AENetRsp 包装）
    4. 支持注册监听器来处理接收到的数据

    使用示例：
        # 创建包装器
        wrapper = AESocketWrapper(client_socket)

        # 注册监听器
        class MyListener(AESocketListener):
            def on_data_received(self, response: AENetRsp):
                print(f"收到数据: {response.data}")

        wrapper.add_listener(MyListener())

        # 开始接收数据
        wrapper.start_receiving()

        # 发送数据
        request = AENetReq(action="test", data={"key": "value"})
        wrapper.send(request)

        # 关闭连接
        wrapper.close()
    """

    def __init__(self, sock: socket.socket, addr: Optional[tuple] = None, buffer_size: int = 10 * 1024 * 1024, is_udp: bool = False):
        """
        初始化 Socket 包装器

        Args:
            sock: 原始 socket 对象
            addr: 连接地址（可选）
            buffer_size: 解析器缓冲区大小（默认 10MB）
            is_udp: 是否为 UDP 模式（默认 False）
        """
        self._socket = sock
        self._addr = addr
        self._is_udp = is_udp
        self._listeners: List[AESocketListener] = []
        self._receive_thread: Optional[threading.Thread] = None
        self._running = False
        self._lock = threading.Lock()

        # 数据包解析器（负责缓存和解析）
        self._parser = AEPacketParser(
            on_request_callback=self._on_request_parsed,
            on_response_callback=self._on_response_parsed,
            on_error_callback=self._on_parser_error,
            buffer_size=buffer_size
        )

        logger.info(f"Socket wrapper created for {addr}, UDP mode: {is_udp}")

    def add_listener(self, listener: AESocketListener) -> None:
        """
        添加数据监听器

        Args:
            listener: 监听器实例
        """
        with self._lock:
            if listener not in self._listeners:
                self._listeners.append(listener)
                logger.debug(f"Listener added: {listener.__class__.__name__}")

    def remove_listener(self, listener: AESocketListener) -> None:
        """
        移除数据监听器

        Args:
            listener: 监听器实例
        """
        with self._lock:
            if listener in self._listeners:
                self._listeners.remove(listener)
                logger.debug(f"Listener removed: {listener.__class__.__name__}")

    def start_receiving(self) -> None:
        """
        开始接收数据

        启动两个组件：
        1. 解析器（独立线程）
        2. 接收线程（从 socket 读取数据，仅 TCP 模式）

        注意：UDP 模式下不启动接收线程，数据由外部通过 feed_data() 喂入
        """
        if self._running:
            logger.warning("Receive thread is already running")
            return

        self._running = True

        # 启动解析器
        self._parser.start()

        # 只在 TCP 模式下启动接收线程
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
        """
        接收线程的主循环

        职责：
        1. 从 socket 快速接收数据
        2. 喂给解析器处理

        不再负责：
        - 缓冲区管理（由 Parser 负责）
        - 数据包解析（由 Parser 负责）
        - JSON 反序列化（由 Parser 负责）
        """
        try:
            while self._running:
                try:
                    # 快速接收数据
                    chunk = self._socket.recv(8192)  # 8KB per chunk
                    if not chunk:
                        logger.info(f"Connection closed by peer: {self._addr}")
                        break

                    # 喂给解析器
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
        """
        解析器回调：收到请求数据

        Args:
            request: 已解析的请求对象
        """
        self._notify_listeners_request(request)

    def _on_response_parsed(self, response: AENetRsp) -> None:
        """
        解析器回调：收到响应数据

        Args:
            response: 已解析的响应对象
        """
        self._notify_listeners(response)

    def _on_parser_error(self, error: Exception) -> None:
        """
        解析器回调：发生错误

        Args:
            error: 异常对象
        """
        self._notify_error(error)

    def feed_data(self, data: bytes) -> None:
        """
        手动喂数据给解析器（用于 UDP 模式）

        Args:
            data: 接收到的数据
        """
        self._parser.feed(data)
        logger.debug(f"Fed {len(data)} bytes to parser")

    def _recv_exact(self, num_bytes: int) -> Optional[bytes]:
        """
        接收精确字节数的数据

        Args:
            num_bytes: 要接收的字节数

        Returns:
            接收到的数据，如果连接关闭则返回 None
        """
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
        """
        发送请求数据

        Args:
            request: 要发送的请求对象
            data_type: 数据类型（默认为 REQUEST）

        Returns:
            是否发送成功
        """
        try:
            # 序列化请求数据（不含旧版的长度前缀）
            data = request.model_dump_json().encode('utf-8')

            # 创建数据包（包含新的包头）
            packet = AEPacket.create(data_type, data)

            # 发送完整数据包
            self._socket.sendall(packet.to_bytes())
            logger.debug(f"Sent request: type={data_type.name}, size={len(data)} bytes")
            return True
        except Exception as e:
            logger.error(f"Failed to send request: {e}")
            self._notify_error(e)
            return False

    def send_response(self, response: AENetRsp) -> bool:
        """
        发送响应数据

        Args:
            response: 要发送的响应对象

        Returns:
            是否发送成功
        """
        try:
            # 序列化响应数据
            data = response.model_dump_json().encode('utf-8')

            # 创建数据包
            packet = AEPacket.create(AEDataType.RESPONSE, data)

            # UDP 和 TCP 使用不同的发送方式
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
        """
        发送心跳包

        Returns:
            是否发送成功
        """
        try:
            # 心跳包不需要数据
            packet = AEPacket.create(AEDataType.HEARTBEAT, b'')
            self._socket.sendall(packet.to_bytes())
            logger.debug("Sent HEARTBEAT")
            return True
        except Exception as e:
            logger.error(f"Failed to send heartbeat: {e}")
            return False

    def send_ping(self) -> bool:
        """
        发送 Ping 包

        Returns:
            是否发送成功
        """
        try:
            packet = AEPacket.create(AEDataType.PING, b'')
            self._socket.sendall(packet.to_bytes())
            logger.debug("Sent PING")
            return True
        except Exception as e:
            logger.error(f"Failed to send ping: {e}")
            return False

    def _send_pong(self) -> bool:
        """
        发送 Pong 包（内部使用，响应 Ping）

        Returns:
            是否发送成功
        """
        try:
            packet = AEPacket.create(AEDataType.PONG, b'')
            self._socket.sendall(packet.to_bytes())
            logger.debug("Sent PONG")
            return True
        except Exception as e:
            logger.error(f"Failed to send pong: {e}")
            return False

    def _handle_heartbeat(self) -> None:
        """处理心跳包（可由子类覆盖）"""
        pass

    def _notify_listeners(self, response: AENetRsp) -> None:
        """
        通知所有监听器响应数据到达

        Args:
            response: 接收到的响应数据
        """
        with self._lock:
            listeners = self._listeners.copy()

        for listener in listeners:
            try:
                listener.on_data_received(response)
            except Exception as e:
                logger.error(f"Error in listener {listener.__class__.__name__}: {e}")

    def _notify_listeners_request(self, request: AENetReq) -> None:
        """
        通知所有监听器请求数据到达

        Args:
            request: 接收到的请求数据
        """
        with self._lock:
            listeners = self._listeners.copy()

        for listener in listeners:
            try:
                # 检查监听器是否有处理请求的方法
                if hasattr(listener, 'on_request_received'):
                    listener.on_request_received(request)
                else:
                    # 如果没有，则包装为响应格式（向后兼容）
                    logger.debug(f"Listener {listener.__class__.__name__} doesn't have on_request_received, skipping")
            except Exception as e:
                logger.error(f"Error in listener {listener.__class__.__name__}: {e}")

    def _notify_connection_closed(self) -> None:
        """
        通知所有监听器连接已关闭
        """
        with self._lock:
            listeners = self._listeners.copy()

        for listener in listeners:
            try:
                listener.on_connection_closed()
            except Exception as e:
                logger.error(f"Error in listener {listener.__class__.__name__}: {e}")

    def _notify_error(self, error: Exception) -> None:
        """
        通知所有监听器发生错误

        Args:
            error: 发生的异常
        """
        with self._lock:
            listeners = self._listeners.copy()

        for listener in listeners:
            try:
                listener.on_error(error)
            except Exception as e:
                logger.error(f"Error in listener {listener.__class__.__name__}: {e}")

    def stop_receiving(self) -> None:
        """停止接收和解析，但不关闭底层 socket"""
        self._running = False
        self._parser.stop()

        if self._receive_thread and self._receive_thread.is_alive():
            self._receive_thread.join(timeout=2.0)

    def close(self) -> None:
        """
        关闭 socket 连接
        """
        logger.info(f"Closing socket connection: {self._addr}")
        self.stop_receiving()

        try:
            self._socket.close()
        except Exception as e:
            logger.error(f"Error closing socket: {e}")

    @property
    def is_connected(self) -> bool:
        """
        检查连接是否仍然活跃

        Returns:
            连接是否活跃
        """
        return self._running and self._socket.fileno() != -1

    @property
    def address(self) -> Optional[tuple]:
        """
        获取连接地址

        Returns:
            连接地址
        """
        return self._addr

    def __enter__(self):
        """支持 with 语句"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """支持 with 语句"""
        self.close()
        return False
