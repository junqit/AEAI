"""
原始 TCP/UDP 客户端 Socket 传输层

职责：
1. 建立到远端的 TCP/UDP 连接（connect / disconnect）
2. 收发原始字节（send / recv 循环）
3. UDP 心跳保活定时（start_heartbeat）
4. 连接状态机 + on_state_changed 回调

不含任何协议解析：收到的原始字节通过 on_data 回调上交，由上层
AEPacketParser（TCP 流）/ AEPacketReceiveBuffer（UDP 数据报）解析。
对标 Swift AENetworkEngine/NetCore/Socket/io 下 TCP/UDP SocketClient 的传输职责。
"""

import socket
import threading
import logging
from enum import Enum
from typing import Optional, Callable

logger = logging.getLogger(__name__)


class AENetSocketType(Enum):
    """Socket 协议类型"""
    TCP = "tcp"
    UDP = "udp"


class AESocketState(Enum):
    """Socket 连接状态"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    FAILED = "failed"


class AESocketError(Exception):
    """Socket 错误（对标 Swift AESocketError）"""

    INVALID_ADDRESS = "invalidAddress"
    CONNECTION_FAILED = "connectionFailed"
    SEND_FAILED = "sendFailed"
    NOT_CONNECTED = "notConnected"
    ENCODING_FAILED = "encodingFailed"

    def __init__(self, code: str, message: str = ""):
        self.code = code
        super().__init__(message or code)


class AENetSocketClient:
    """
    原始 TCP/UDP 客户端 Socket

    - TCP：SOCK_STREAM，connect 后 recv 循环；recv 返回 b'' 表示对端关闭
    - UDP：SOCK_DGRAM，connect 仅设置默认对端（无握手）；recvfrom 循环；可选心跳保活
    - 收到的原始字节经 on_data 回调上交；不含协议解析
    """

    RECV_BUF_SIZE = 65536

    def __init__(self, ip: str, port: int,
                 protocol_type: AENetSocketType = AENetSocketType.TCP,
                 connect_timeout: float = 10.0):
        self.ip = ip
        self.port = port
        self.protocol_type = protocol_type
        self._connect_timeout = connect_timeout

        self._sock: Optional[socket.socket] = None
        self._state = AESocketState.DISCONNECTED
        self._state_lock = threading.Lock()

        self._running = False
        self._recv_thread: Optional[threading.Thread] = None
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._heartbeat_stop = threading.Event()
        self._heartbeat_interval: float = 15.0
        self._beat: Optional[Callable[[], None]] = None

        # 回调
        self.on_state_changed: Optional[Callable[[AESocketState], None]] = None
        self._on_data: Optional[Callable[[bytes], None]] = None
        self._on_closed: Optional[Callable[[], None]] = None

    # ==================== 状态 ====================

    @property
    def state(self) -> AESocketState:
        with self._state_lock:
            return self._state

    def _set_state(self, state: AESocketState) -> None:
        with self._state_lock:
            self._state = state
        if self.on_state_changed:
            try:
                self.on_state_changed(state)
            except Exception as e:
                logger.error("[AENetSocketClient] on_state_changed 异常: %s", e, exc_info=True)

    # ==================== 连接 ====================

    def connect(self) -> None:
        """阻塞连接（应在 executor 线程中调用，勿在事件循环线程直接调用）。"""
        if self.state in (AESocketState.CONNECTING, AESocketState.CONNECTED):
            logger.warning("[AENetSocketClient] 已连接或连接中，跳过重复连接")
            return

        self._set_state(AESocketState.CONNECTING)

        try:
            if self.protocol_type == AENetSocketType.TCP:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(self._connect_timeout)
                sock.connect((self.ip, self.port))
                sock.settimeout(None)  # 恢复阻塞，供 recv 循环使用
            else:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.connect((self.ip, self.port))  # UDP：仅设置默认对端，无握手
            self._sock = sock
            self._running = True
        except OSError as e:
            self._set_state(AESocketState.FAILED)
            raise AESocketError(AESocketError.CONNECTION_FAILED,
                                 f"连接 {self.ip}:{self.port} 失败: {e}") from e

        self._set_state(AESocketState.CONNECTED)
        logger.info("[AENetSocketClient] 连接成功 %s:%d (%s)",
                    self.ip, self.port, self.protocol_type.value)

    def disconnect(self) -> None:
        """断开：停止收发心跳线程、关闭 socket、置 DISCONNECTED。"""
        self._running = False
        self._stop_heartbeat()

        if self._sock is not None:
            try:
                self._sock.close()
            except Exception as e:
                logger.error("[AENetSocketClient] 关闭 socket 异常: %s", e)
            self._sock = None

        if self._recv_thread and self._recv_thread.is_alive():
            self._recv_thread.join(timeout=2.0)

        self._set_state(AESocketState.DISCONNECTED)
        logger.info("[AENetSocketClient] 已断开 %s:%d", self.ip, self.port)

    # ==================== 发送 ====================

    def send(self, data: bytes) -> None:
        """发送原始字节（TCP: sendall；UDP: send）。"""
        if self.state != AESocketState.CONNECTED:
            raise AESocketError(AESocketError.NOT_CONNECTED, "未连接，发送失败")
        try:
            if self.protocol_type == AENetSocketType.TCP:
                self._sock.sendall(data)
            else:
                self._sock.send(data)
        except OSError as e:
            self._set_state(AESocketState.FAILED)
            raise AESocketError(AESocketError.SEND_FAILED, f"发送失败: {e}") from e

    # ==================== 接收 ====================

    def start_receiving(self,
                        on_data: Callable[[bytes], None],
                        on_closed: Callable[[], None]) -> None:
        """启动接收线程：收到数据回调 on_data；对端关闭/出错回调 on_closed。"""
        self._on_data = on_data
        self._on_closed = on_closed
        self._recv_thread = threading.Thread(
            target=self._recv_loop,
            daemon=True,
            name=f"AE-{self.protocol_type.value}-recv",
        )
        self._recv_thread.start()

    def _recv_loop(self) -> None:
        while self._running:
            try:
                if self.protocol_type == AENetSocketType.TCP:
                    data = self._sock.recv(self.RECV_BUF_SIZE)
                    if not data:
                        # TCP 对端关闭
                        logger.info("[AENetSocketClient] TCP 对端关闭 %s:%d", self.ip, self.port)
                        self._running = False
                        self._set_state(AESocketState.DISCONNECTED)
                        self._safe_call(self._on_closed)
                        return
                else:
                    data, _ = self._sock.recvfrom(self.RECV_BUF_SIZE)
                if self._on_data:
                    self._on_data(data)
            except OSError as e:
                if self._running:
                    logger.error("[AENetSocketClient] 接收错误: %s", e)
                    self._running = False
                    self._set_state(AESocketState.FAILED)
                    self._safe_call(self._on_closed)
                return

    @staticmethod
    def _safe_call(cb: Optional[Callable[[], None]]) -> None:
        if cb:
            try:
                cb()
            except Exception as e:
                logger.error("[AENetSocketClient] 回调异常: %s", e, exc_info=True)

    # ==================== 心跳（仅 UDP 保活） ====================

    def start_heartbeat(self, interval: float, beat: Callable[[], None]) -> None:
        """启动定时心跳线程：每 interval 秒调用 beat()。"""
        self._heartbeat_interval = interval
        self._beat = beat
        self._heartbeat_stop.clear()
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            daemon=True,
            name="AE-heartbeat",
        )
        self._heartbeat_thread.start()
        logger.info("[AENetSocketClient] 心跳已启动，间隔 %ss", interval)

    def stop_heartbeat(self) -> None:
        self._stop_heartbeat()

    def _stop_heartbeat(self) -> None:
        self._heartbeat_stop.set()
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            self._heartbeat_thread.join(timeout=2.0)
        self._heartbeat_thread = None

    def _heartbeat_loop(self) -> None:
        while not self._heartbeat_stop.wait(self._heartbeat_interval):
            try:
                if self._beat:
                    self._beat()
            except Exception as e:
                logger.error("[AENetSocketClient] 心跳异常: %s", e, exc_info=True)
                return
