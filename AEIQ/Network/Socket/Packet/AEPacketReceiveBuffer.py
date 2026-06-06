"""
AEPacket 接收缓冲区

职责：
1. receive() 收到数据即入队通知解析线程，socket 立即接收下一条
2. 解析线程串行：data → AEPacket → AEDataType 对应消息体 → 回调上层
"""

import threading
import logging
from queue import Queue, Empty
from typing import Callable, Optional, Tuple, Union
from dataclasses import dataclass

from .AEPacket import AEPacketHeader, AEPacket, AEDataType, calculate_crc16
from ...Core import AENetReq, AENetRsp

logger = logging.getLogger(__name__)


@dataclass
class ParsedPacketResult:
    """解析完成的消息体"""
    data_type: AEDataType
    payload: Union[AENetReq, AENetRsp, bytes]
    client_addr: tuple
    raw_data: bytes


PacketReceivedCallback = Callable[[ParsedPacketResult], None]


class AEPacketReceiveBuffer:
    """
    AEPacket UDP 接收缓冲区

    - receive(): 入队 + 通知，立即返回
    - 解析线程: 串行 data → AEPacket → AEDataType 消息体 → 回调上层
    """

    def __init__(self,
                 on_packet_received: Optional[PacketReceivedCallback] = None):
        self._receive_queue: Queue[Tuple[bytes, tuple]] = Queue()
        self._data_event = threading.Event()

        self._on_packet_received = on_packet_received

        self._running = False
        self._parse_thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._running:
            return

        self._running = True

        self._parse_thread = threading.Thread(
            target=self._parse_loop,
            daemon=True,
            name="AEPacketParseThread"
        )
        self._parse_thread.start()

        logger.info("AEPacketReceiveBuffer started")

    def stop(self) -> None:
        self._running = False
        self._data_event.set()

        if self._parse_thread and self._parse_thread.is_alive():
            self._parse_thread.join(timeout=2.0)

        logger.info("AEPacketReceiveBuffer stopped")

    def set_callback(self, callback: PacketReceivedCallback) -> None:
        self._on_packet_received = callback

    def receive(self, data: bytes, client_addr: tuple) -> None:
        """收到数据即入队并通知解析线程，立即返回。"""
        self._receive_queue.put_nowait((data, client_addr))
        self._data_event.set()

    # ==================== 串行解析线程 ====================

    def _parse_loop(self) -> None:
        """串行: data → AEPacket → 分发"""
        while self._running:
            self._data_event.wait(timeout=1.0)
            self._data_event.clear()

            while self._running:
                try:
                    data, client_addr = self._receive_queue.get_nowait()
                except Empty:
                    break

                self._process_data(data, client_addr)

    def _process_data(self, data: bytes, client_addr: tuple) -> None:
        """data → 解析包头 → 校验 CRC → AEPacket → 分发"""
        if len(data) < AEPacketHeader.HEADER_SIZE:
            logger.warning(f"Datagram too small ({len(data)} bytes) from {client_addr}")
            return

        try:
            header = AEPacketHeader.from_bytes(data[:AEPacketHeader.HEADER_SIZE])
        except ValueError as e:
            logger.warning(f"Invalid header from {client_addr}: {e}")
            return

        payload_data = data[AEPacketHeader.HEADER_SIZE:]

        actual_crc = calculate_crc16(payload_data)
        if actual_crc != header.checksum:
            logger.error(
                f"CRC mismatch from {client_addr}: "
                f"expected 0x{header.checksum:04X}, got 0x{actual_crc:04X}"
            )
            return

        packet = AEPacket(header=header, data=payload_data)
        self._dispatch_packet(packet, client_addr)

    # ==================== 异步分发 ====================

    def _dispatch_packet(self, packet: AEPacket, client_addr: tuple) -> None:
        """AEPacket → AEDataType 对应消息体 → 回调上层"""
        data_type_value = packet.header.data_type

        try:
            if data_type_value == AEDataType.REQUEST.value:
                payload = AENetReq.from_bytes(packet.data)
                ae_type = AEDataType.REQUEST
            elif data_type_value == AEDataType.RESPONSE.value:
                payload = AENetRsp.from_bytes(packet.data)
                ae_type = AEDataType.RESPONSE
            elif data_type_value == AEDataType.HEARTBEAT.value:
                payload = packet.data
                ae_type = AEDataType.HEARTBEAT
            elif data_type_value == AEDataType.PING.value:
                payload = packet.data
                ae_type = AEDataType.PING
            elif data_type_value == AEDataType.PONG.value:
                payload = packet.data
                ae_type = AEDataType.PONG
            else:
                logger.warning(f"Unknown data type: 0x{data_type_value:04X}")
                return

            result = ParsedPacketResult(
                data_type=ae_type,
                payload=payload,
                client_addr=client_addr,
                raw_data=packet.data
            )

            if self._on_packet_received:
                self._on_packet_received(result)

        except Exception as e:
            logger.error(f"Error dispatching packet from {client_addr}: {e}", exc_info=True)
