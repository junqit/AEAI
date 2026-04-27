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

    def __init__(self, max_buffer_size: int = 10 * 1024 * 1024):  # 默认 10MB
        """
        初始化接收缓冲区

        Args:
            max_buffer_size: 最大缓冲区大小（字节），防止内存溢出
        """
        self._buffer = bytearray()
        self._max_buffer_size = max_buffer_size

    def append(self, data: bytes) -> None:
        """
        向缓冲区追加数据

        Args:
            data: 接收到的数据

        Raises:
            OverflowError: 如果缓冲区超过最大限制
        """
        if len(self._buffer) + len(data) > self._max_buffer_size:
            raise OverflowError(
                f"接收缓冲区溢出: 当前 {len(self._buffer)} + 新增 {len(data)} "
                f"> 最大限制 {self._max_buffer_size}"
            )
        self._buffer.extend(data)
        logger.debug(f"Buffer append {len(data)} bytes, total: {len(self._buffer)}")

    def try_parse_packet(self) -> Optional[AEPacket]:
        """
        尝试从缓冲区解析一个完整的数据包

        Returns:
            如果成功解析返回数据包，否则返回 None

        工作流程：
        1. 检查缓冲区是否有足够的数据解析包头（16字节）
        2. 解析包头
        3. 检查缓冲区是否有完整的数据
        4. 解析完整数据包
        5. 从缓冲区移除已解析的数据
        """
        # 1. 检查是否有足够的数据解析包头
        if len(self._buffer) < AEPacketHeader.HEADER_SIZE:
            logger.debug(f"Buffer too small for header: {len(self._buffer)} < {AEPacketHeader.HEADER_SIZE}")
            return None

        try:
            # 2. 解析包头（但不移除数据）
            header = AEPacketHeader.from_bytes(bytes(self._buffer[:AEPacketHeader.HEADER_SIZE]))
            logger.debug(f"Parsed header: type=0x{header.data_type:04X}, length={header.length}")

            # 检查数据长度是否合理（防止恶意数据）
            if header.length > self._max_buffer_size:
                raise ValueError(f"数据长度过大: {header.length} > {self._max_buffer_size}")

            # 3. 检查是否有完整的数据包
            total_packet_size = AEPacketHeader.HEADER_SIZE + header.length
            if len(self._buffer) < total_packet_size:
                logger.debug(f"Incomplete packet: {len(self._buffer)} < {total_packet_size}")
                return None

            # 4. 提取数据部分
            data_start = AEPacketHeader.HEADER_SIZE
            data_end = total_packet_size
            data = bytes(self._buffer[data_start:data_end])

            # 5. 创建数据包（包含校验）
            packet = AEPacket.from_bytes(header, data)

            # 6. 从缓冲区移除已处理的数据
            self._buffer = self._buffer[total_packet_size:]
            logger.debug(f"Packet parsed successfully, remaining buffer: {len(self._buffer)} bytes")

            return packet

        except ValueError as e:
            # 如果解析失败，说明可能收到了无效数据
            logger.error(f"数据包解析失败: {e}")
            # 尝试查找下一个有效的魔数
            self._skip_to_next_magic_code()
            return None

    def _skip_to_next_magic_code(self) -> None:
        """
        跳过无效数据，查找下一个有效的魔数

        这个方法用于错误恢复，当遇到无效数据包时，
        尝试在缓冲区中查找下一个可能的有效包头
        """
        from .AEPacket import MAGIC_CODE

        magic_bytes = MAGIC_CODE.to_bytes(4, byteorder='big')

        # 从位置 1 开始查找（跳过当前位置）
        for i in range(1, len(self._buffer) - 3):
            if self._buffer[i:i+4] == magic_bytes:
                logger.warning(f"Found next magic code at offset {i}, skipping {i} bytes")
                self._buffer = self._buffer[i:]
                return

        # 如果没找到，清空整个缓冲区
        logger.warning("No valid magic code found, clearing buffer")
        self._buffer.clear()

    def clear(self) -> None:
        """清空缓冲区"""
        self._buffer.clear()
        logger.debug("Buffer cleared")

    @property
    def size(self) -> int:
        """获取当前缓冲区大小"""
        return len(self._buffer)

    def __len__(self) -> int:
        """获取缓冲区大小"""
        return len(self._buffer)
