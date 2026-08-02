"""
数据包解析器

职责：
1. 管理接收缓冲区
2. 在独立线程中解析数据包
3. 通过回调通知已解析的数据
"""

import threading
import logging
from typing import Callable, Dict, Optional
from .AEReceiveBuffer import AEReceiveBuffer
from .AEPacket import AEPacket, AEDataType, UNIQUE_ID_SENTINEL
from .AEPacketPool import AEPacketPool
from ...Core import AENetReq, AENetRsp

logger = logging.getLogger(__name__)


class AEPacketParser:
    """
    数据包解析器

    功能：
    1. 接收原始字节数据
    2. 缓存到接收缓冲区
    3. 在独立线程中解析完整数据包
    4. 根据类型解析为 AENetReq 或 AENetRsp
    5. 通过回调通知业务层
    """

    def __init__(self,
                 on_request_callback: Optional[Callable[[AENetReq], None]] = None,
                 on_response_callback: Optional[Callable[[AENetRsp], None]] = None,
                 on_error_callback: Optional[Callable[[Exception], None]] = None,
                 buffer_size: int = 10 * 1024 * 1024):
        self._buffer = AEReceiveBuffer(max_buffer_size=buffer_size)
        self._buffer_lock = threading.Lock()

        self._parse_thread: Optional[threading.Thread] = None
        self._running = False

        self._data_available = threading.Event()

        self._on_request_callback = on_request_callback
        self._on_response_callback = on_response_callback
        self._on_error_callback = on_error_callback

        # 分片重组：unique_id -> AEPacketPool；解析线程单线程访问，无需加锁
        self._packet_pools: Dict[int, AEPacketPool] = {}


    def start(self) -> None:
        if self._running:
            logger.warning("Parser thread is already running")
            return

        self._running = True
        self._parse_thread = threading.Thread(
            target=self._parse_loop,
            daemon=True,
            name="PacketParser"
        )
        self._parse_thread.start()

    def stop(self) -> None:
        self._running = False

        self._data_available.set()

        if self._parse_thread and self._parse_thread.is_alive():
            self._parse_thread.join(timeout=2.0)

        with self._buffer_lock:
            self._buffer.clear()

        self._packet_pools.clear()


    def feed(self, data: bytes) -> None:
        if not self._running:
            logger.warning("Parser is not running, data discarded")
            return

        try:
            with self._buffer_lock:
                self._buffer.append(data)


            self._data_available.set()

        except OverflowError as e:
            logger.error(f"Buffer overflow: {e}")
            with self._buffer_lock:
                self._buffer.clear()
            self._notify_error(e)

        except Exception as e:
            logger.error(f"Error feeding data: {e}")
            self._notify_error(e)

    def _parse_loop(self) -> None:
        try:
            while self._running:
                if not self._data_available.wait():
                    continue

                self._data_available.clear()

                while self._running:
                    try:
                        with self._buffer_lock:
                            packet = self._buffer.try_parse_packet()

                        if packet is None:
                            break


                        self._handle_packet(packet)

                    except ValueError as e:
                        logger.error(f"Failed to parse packet: {e}")
                        self._notify_error(e)
                        continue

                    except Exception as e:
                        logger.error(f"Error handling packet: {e}")
                        self._notify_error(e)
                        continue

        except Exception as e:
            logger.error(f"Error in parse loop: {e}")
            self._notify_error(e)
        finally:
            pass

    def _handle_packet(self, packet: AEPacket) -> None:
        unique_id = packet.header.unique_id

        # 非分片单包：直接按类型分发
        if unique_id == UNIQUE_ID_SENTINEL:
            self._dispatch_by_type(packet.header.data_type_value, packet.data)
            return

        # 分片包：按 unique_id 收集，收齐后拼装再分发
        self._handle_fragment(packet)

    def _handle_fragment(self, packet: AEPacket) -> None:
        unique_id = packet.header.unique_id

        pool = self._packet_pools.get(unique_id)
        if pool is None:
            # 首个分片：传入构造函数
            pool = AEPacketPool(unique_id=unique_id, packet=packet)
            self._packet_pools[unique_id] = pool
        else:
            pool.add(packet)

        # 每收到一包都检测是否已完整
        if pool.is_complete():
            assembled = pool.assemble()
            data_type_value = pool.data_type_value
            last_seq = pool.last_seq
            # 清理
            self._packet_pools.pop(unique_id, None)
            self._dispatch_by_type(data_type_value, assembled)

    def _dispatch_by_type(self, data_type_value: int, data: bytes) -> None:
        try:
            if data_type_value == AEDataType.REQUEST.value:
                request = AENetReq.from_bytes(data)
                self._notify_request(request)

            elif data_type_value == AEDataType.RESPONSE.value:
                response = AENetRsp.from_bytes(data)
                self._notify_response(response)

            elif data_type_value == AEDataType.HEARTBEAT.value:
                pass
            elif data_type_value == AEDataType.PING.value:
                pass
            elif data_type_value == AEDataType.PONG.value:
                pass
            else:
                logger.warning(f"Unknown data type: 0x{data_type_value:04X}")

        except Exception as e:
            logger.error(f"Error parsing packet data: {e}")
            self._notify_error(e)

    def _notify_request(self, request: AENetReq) -> None:
        if self._on_request_callback:
            try:
                self._on_request_callback(request)
            except Exception as e:
                logger.error(f"Error in request callback: {e}")

    def _notify_response(self, response: AENetRsp) -> None:
        if self._on_response_callback:
            try:
                self._on_response_callback(response)
            except Exception as e:
                logger.error(f"Error in response callback: {e}")

    def _notify_error(self, error: Exception) -> None:
        if self._on_error_callback:
            try:
                self._on_error_callback(error)
            except Exception as e:
                logger.error(f"Error in error callback: {e}")

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def buffer_size(self) -> int:
        with self._buffer_lock:
            return self._buffer.size

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
        return False
