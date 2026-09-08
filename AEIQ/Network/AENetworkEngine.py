"""
AENetworkEngine — 出站客户端网络引擎

对标 Swift AENetSocketEngine：connect/disconnect/状态机/串行分包发送/
异步接收解析/请求-响应匹配(requestId)/UDP 心跳保活。

混合并发模型：
- 阻塞 socket + 接收/发送/心跳/解析线程（复用 AEPacketParser / AEPacketReceiveBuffer）
- 通过 asyncio.Future + loop.call_soon_threadsafe 桥接到 asyncio，
  使业务层可直接 `await engine.send(req) -> AENetRsp`

复用现有组件，不引入协议副本：
- 发送分包：AEPacket.packets_from_data
- TCP 流解析：AEPacketParser（on_response / on_request 回调）
- UDP 数据报解析：AEPacketReceiveBuffer（on_packet_received 回调）
- 数据模型：AENetReq / AENetRsp（to_bytes / from_bytes，req.requestId 匹配）
"""

import asyncio
import threading
import time
import logging
from queue import Queue, Empty
from typing import Optional, Callable, Dict

from .Socket.Packet.AEPacket import AEPacket, AEDataType
from .Socket.Packet.AEPacketParser import AEPacketParser
from .Socket.Packet.AEPacketReceiveBuffer import AEPacketReceiveBuffer, ParsedPacketResult
from .Core.AENetReq import AENetReq, AENetReqInfo
from .Core.AENetRsp import AENetRsp
from .Socket.Connection.AENetSocketClient import (
    AENetSocketClient, AENetSocketType, AESocketState, AESocketError,
)

logger = logging.getLogger(__name__)


class AENetworkEngine:
    """
    出站客户端网络引擎

    使用：
        engine = AENetworkEngine("10.0.0.1", 8888, AENetSocketType.UDP)
        await engine.connect()
        rsp: AENetRsp = await engine.send(req)          # 自动生成 requestId 并等待匹配响应
        await engine.disconnect()

    回调（均在工作线程触发；勿在其中 await）：
        on_state_changed(state)        连接状态变更
        on_response_received(rsp)      未匹配到 pending 的响应（服务端主动推送）
        on_request_received(req)        对端主动下发的请求
    """

    def __init__(self, ip: str, port: int,
                 protocol_type: AENetSocketType = AENetSocketType.UDP,
                 heartbeat_interval: float = 15.0):
        self._ip = ip
        self._port = port
        self._protocol_type = protocol_type
        self._heartbeat_interval = heartbeat_interval

        self._client = AENetSocketClient(ip, port, protocol_type)
        self._client.on_state_changed = self._on_client_state

        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._pending: Dict[str, asyncio.Future] = {}
        self._pending_lock = threading.Lock()

        self._send_queue: "Queue[Optional[tuple]]" = Queue()
        self._send_thread: Optional[threading.Thread] = None
        self._running = False

        self._state = AESocketState.DISCONNECTED
        self._state_lock = threading.Lock()

        # 复用的解析器
        self._parser: Optional[AEPacketParser] = None          # TCP 流
        self._udp_buffer: Optional[AEPacketReceiveBuffer] = None  # UDP 数据报

        # 公开回调
        self.on_state_changed: Optional[Callable[[AESocketState], None]] = None
        self.on_response_received: Optional[Callable[[AENetRsp], None]] = None
        self.on_request_received: Optional[Callable[[AENetReq], None]] = None

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
                logger.error("[AENetworkEngine] on_state_changed 异常: %s", e, exc_info=True)

    def _on_client_state(self, state: AESocketState) -> None:
        """传输层状态镜像到引擎状态。"""
        self._set_state(state)

    # ==================== 连接 ====================

    async def connect(self) -> None:
        """连接远端。在事件循环线程外（executor）执行阻塞 connect；成功后启动收发线程。"""
        self._loop = asyncio.get_running_loop()

        try:
            await self._loop.run_in_executor(None, self._client.connect)
        except AESocketError:
            # client 已置 FAILED 并经 on_state_changed 镜像
            raise

        # 初始化解析器 + 接收线程
        if self._protocol_type == AENetSocketType.TCP:
            self._parser = AEPacketParser(
                on_request_callback=self._on_request,
                on_response_callback=self._on_response,
                on_error_callback=self._on_parse_error,
            )
            self._parser.start()
            self._client.start_receiving(
                on_data=self._parser.feed,
                on_closed=self._on_peer_closed,
            )
        else:
            self._udp_buffer = AEPacketReceiveBuffer(
                on_packet_received=self._on_parsed_result
            )
            self._udp_buffer.start()
            peer_addr = (self._ip, self._port)
            self._client.start_receiving(
                on_data=lambda data: self._udp_buffer.receive(data, peer_addr),
                on_closed=self._on_peer_closed,
            )
            self._client.start_heartbeat(self._heartbeat_interval, self._send_heartbeat)

        # 串行发送队列线程
        self._running = True
        self._send_thread = threading.Thread(
            target=self._send_loop, daemon=True, name="AE-network-send"
        )
        self._send_thread.start()

    async def disconnect(self) -> None:
        """断开：停传输/解析线程、排空发送队列、取消所有 pending Future。"""
        self._running = False
        self._client.disconnect()
        if self._parser is not None:
            self._parser.stop()
        if self._udp_buffer is not None:
            self._udp_buffer.stop()

        # 排空发送队列
        while True:
            try:
                self._send_queue.get_nowait()
            except Empty:
                break

        self._cancel_pending("disconnect")

        if self._send_thread and self._send_thread.is_alive():
            self._send_thread.join(timeout=2.0)

    def close(self) -> None:
        """同步尽力清理（用于 __del__ 或不可 await 的场景）。"""
        self._running = False
        try:
            self._client.disconnect()
        except Exception as e:
            logger.error("[AENetworkEngine] close disconnect 异常: %s", e)
        if self._parser is not None:
            try: self._parser.stop()
            except Exception: pass
        if self._udp_buffer is not None:
            try: self._udp_buffer.stop()
            except Exception: pass
        self._cancel_pending("close")

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    # ==================== 发送 ====================

    async def send(self, request: AENetReq) -> AENetRsp:
        """发送请求并等待匹配响应（按 req.requestId）。requestId 缺省时自动生成。"""
        if self.state != AESocketState.CONNECTED:
            raise AESocketError(AESocketError.NOT_CONNECTED, "未连接，发送失败")

        self._ensure_request_id(request)
        request_id = request.req.requestId

        future = self._loop.create_future()
        with self._pending_lock:
            self._pending[request_id] = future

        self._enqueue_package(AEDataType.REQUEST, request.to_bytes())
        return await future

    def send_nowait(self, request: AENetReq) -> None:
        """发送请求不等待（fire-and-forget）。requestId 缺省时自动生成。"""
        if self.state != AESocketState.CONNECTED:
            raise AESocketError(AESocketError.NOT_CONNECTED, "未连接，发送失败")
        self._ensure_request_id(request)
        self._enqueue_package(AEDataType.REQUEST, request.to_bytes())

    def _ensure_request_id(self, request: AENetReq) -> None:
        if request.req is None:
            request.req = AENetReqInfo()
        if not request.req.requestId:
            request.req.requestId = self._generate_request_id()

    _counter = 0
    _counter_lock = threading.Lock()

    @classmethod
    def _generate_request_id(cls) -> str:
        """生成 8 位十六进制 requestId（对标 Swift AENetReq.generateRequestId：CRC32 风格）。"""
        with cls._counter_lock:
            cls._counter = (cls._counter + 1) & 0xFFFFFFFF
            c = cls._counter
        seed = (int(time.time()) & 0xFFFFFFFF) ^ c
        crc = seed ^ 0xFFFFFFFF
        for _ in range(32):
            if crc & 1:
                crc = (crc >> 1) ^ 0xEDB88320
            else:
                crc = crc >> 1
        crc ^= 0xFFFFFFFF
        return f"{crc & 0xFFFFFFFF:08x}"

    def _enqueue_package(self, data_type: AEDataType, data: bytes) -> None:
        self._send_queue.put((data_type, data))

    def _send_loop(self) -> None:
        """串行发送：一次取一个 package，分包后逐包下发；失败则失败所有 pending。"""
        while self._running:
            try:
                item = self._send_queue.get(timeout=0.5)
            except Empty:
                continue
            if item is None:
                return
            data_type, data = item
            try:
                packets = AEPacket.packets_from_data(data_type, data)
                for packet in packets:
                    self._client.send(packet.to_bytes())
            except AESocketError as e:
                logger.error("[AENetworkEngine] 数据包发送失败: %s", e)
                self._client.stop_heartbeat()
                self._fail_pending(e)
                return
            except Exception as e:
                logger.error("[AENetworkEngine] 发送异常: %s", e, exc_info=True)
                self._client.stop_heartbeat()
                self._fail_pending(AESocketError(AESocketError.SEND_FAILED, str(e)))
                return

    # ==================== 接收（解析器回调，工作线程触发） ====================

    def _on_parsed_result(self, result: ParsedPacketResult) -> None:
        """UDP：AEPacketReceiveBuffer 解析完成回调。"""
        if result.data_type == AEDataType.RESPONSE:
            self._on_response(result.payload)
        elif result.data_type == AEDataType.REQUEST:
            self._on_request(result.payload)

    def _on_response(self, rsp: AENetRsp) -> None:
        """TCP/UDP：收到响应，桥接到事件循环线程匹配 pending。"""
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._resolve, rsp)

    def _on_request(self, req: AENetReq) -> None:
        """TCP/UDP：收到对端主动请求，桥接到事件循环线程。"""
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._dispatch_request, req)

    def _on_parse_error(self, error: Exception) -> None:
        logger.error("[AENetworkEngine] 解析错误: %s", error, exc_info=True)

    def _on_peer_closed(self) -> None:
        """TCP 对端关闭：取消所有 pending Future。状态由 client 回调置为 DISCONNECTED。"""
        self._cancel_pending("peer closed")

    # ==================== 请求/响应匹配（事件循环线程） ====================

    def _resolve(self, rsp: AENetRsp) -> None:
        request_id = rsp.req.requestId if rsp.req else None
        future = None
        with self._pending_lock:
            if request_id:
                future = self._pending.pop(request_id, None)
        if future is not None and not future.done():
            future.set_result(rsp)
        elif self.on_response_received:
            try:
                self.on_response_received(rsp)
            except Exception as e:
                logger.error("[AENetworkEngine] on_response_received 异常: %s", e, exc_info=True)

    def _dispatch_request(self, req: AENetReq) -> None:
        if self.on_request_received:
            try:
                self.on_request_received(req)
            except Exception as e:
                logger.error("[AENetworkEngine] on_request_received 异常: %s", e, exc_info=True)

    # ==================== pending Future 失败/取消 ====================

    def _fail_pending(self, exc: BaseException) -> None:
        """所有 pending Future 设置异常（在事件循环线程执行）。"""
        with self._pending_lock:
            futures = list(self._pending.values())
            self._pending.clear()
        if self._loop and self._loop.is_running():
            for f in futures:
                self._loop.call_soon_threadsafe(self._set_future_exception, f, exc)

    def _cancel_pending(self, reason: str) -> None:
        """所有 pending Future 取消（在事件循环线程执行）。"""
        with self._pending_lock:
            futures = list(self._pending.values())
            self._pending.clear()
        if self._loop and self._loop.is_running():
            for f in futures:
                self._loop.call_soon_threadsafe(self._cancel_future, f)
        logger.info("[AENetworkEngine] pending 已取消（%s），共 %d 个", reason, len(futures))

    @staticmethod
    def _set_future_exception(future: asyncio.Future, exc: BaseException) -> None:
        if not future.done():
            future.set_exception(exc)

    @staticmethod
    def _cancel_future(future: asyncio.Future) -> None:
        if not future.done():
            future.cancel()

    # ==================== 心跳（UDP 保活） ====================

    def _send_heartbeat(self) -> None:
        """发送心跳包，复用同一串行发送队列。对标 Swift sendHeartbeat。"""
        self._enqueue_package(AEDataType.HEARTBEAT, b"{}")
