"""
接收缓冲区管理

用于处理 socket 数据的粘包和半包问题
"""

import logging
from typing import Optional
from .AEPacket import AEPacketHeader, AEPacket

logger = logging.getLogger(__name__)


class AEReceiveBuffer:
    """
    接收缓冲区

    功能：
    1. 缓存接收到的数据
    2. 解析完整的数据包
    3. 处理粘包和半包问题
    """

    def __init__(self, max_buffer_size: int = 10 * 1024 * 1024):
        self._buffer = bytearray()
        self._max_buffer_size = max_buffer_size

    def append(self, data: bytes) -> None:
        if len(self._buffer) + len(data) > self._max_buffer_size:
            raise OverflowError(
                f"接收缓冲区溢出: 当前 {len(self._buffer)} + 新增 {len(data)} "
                f"> 最大限制 {self._max_buffer_size}"
            )
        self._buffer.extend(data)

    def try_parse_packet(self) -> Optional[AEPacket]:
        if len(self._buffer) < AEPacketHeader.HEADER_SIZE:
            return None

        try:
            header = AEPacketHeader.from_bytes(bytes(self._buffer[:AEPacketHeader.HEADER_SIZE]))

            if header.length > self._max_buffer_size:
                raise ValueError(f"数据长度过大: {header.length} > {self._max_buffer_size}")

            total_packet_size = AEPacketHeader.HEADER_SIZE + header.length
            if len(self._buffer) < total_packet_size:
                return None

            data_start = AEPacketHeader.HEADER_SIZE
            data_end = total_packet_size
            data = bytes(self._buffer[data_start:data_end])

            packet = AEPacket.from_bytes(header, data)

            self._buffer = self._buffer[total_packet_size:]

            return packet

        except ValueError as e:
            logger.error(f"数据包解析失败: {e}")
            self._skip_to_next_magic_code()
            return None

    def _skip_to_next_magic_code(self) -> None:
        from .AEPacket import MAGIC_CODE

        magic_bytes = MAGIC_CODE.to_bytes(4, byteorder='big')

        for i in range(1, len(self._buffer) - 3):
            if self._buffer[i:i+4] == magic_bytes:
                logger.warning(f"Found next magic code at offset {i}, skipping {i} bytes")
                self._buffer = self._buffer[i:]
                return

        logger.warning("No valid magic code found, clearing buffer")
        self._buffer.clear()

    def clear(self) -> None:
        self._buffer.clear()

    @property
    def size(self) -> int:
        return len(self._buffer)

    def __len__(self) -> int:
        return len(self._buffer)
