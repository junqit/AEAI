"""
网络数据包协议定义

包结构：
┌─────────────┬──────────┬──────────┬──────────┬──────────┐
│ Magic Code  │ DataType │  Length  │ Checksum │   Data   │
│   (2 bytes) │ (2 bytes)│ (4 bytes)│ (2 bytes)│ (N bytes)│
└─────────────┴──────────┴──────────┴──────────┴──────────┘

总包头长度: 10 bytes
"""

from enum import Enum
from typing import Optional, ClassVar
from pydantic import BaseModel
import struct
import zlib


# 魔数：使用不会在正常数据中出现的字符组合
# 0x1E = ASCII Record Separator (RS) 控制字符
# 0xAE = 扩展ASCII字符
# 这个组合在正常的文本/JSON数据中不会出现
MAGIC_CODE = 0x1EAE


class AEDataType(Enum):
    """数据类型枚举"""
    REQUEST = 0x0001    # 请求数据 (AENetReq)
    RESPONSE = 0x0002   # 响应数据 (AENetRsp)
    HEARTBEAT = 0x0003  # 心跳包
    PING = 0x0004       # Ping
    PONG = 0x0005       # Pong
    CUSTOM = 0x00FF     # 自定义数据


class AEPacketHeader(BaseModel):
    """
    数据包头结构

    字段说明：
    - magic_code: 魔数，固定为 0x4145 ('AE')，2字节
    - data_type: 数据类型，2字节
    - length: 数据长度（不包含包头），4字节
    - checksum: 数据校验和（CRC16），2字节
    """
    magic_code: int = MAGIC_CODE
    data_type: int  # AEDataType
    length: int
    checksum: int

    # 包头固定长度 - 使用 ClassVar
    HEADER_SIZE: ClassVar[int] = 10  # 2 + 2 + 4 + 2

    # 包头格式：大端序 - 使用 ClassVar
    # H = unsigned short (2 bytes)
    # I = unsigned int (4 bytes)
    HEADER_FORMAT: ClassVar[str] = '!HHIH'  # ! = 网络字节序(大端)

    @classmethod
    def from_bytes(cls, data: bytes) -> 'AEPacketHeader':
        """
        从字节流解析包头

        Args:
            data: 至少 10 字节的数据

        Returns:
            解析后的包头对象

        Raises:
            ValueError: 如果数据长度不足或魔数不匹配
        """
        if len(data) < cls.HEADER_SIZE:
            raise ValueError(f"数据长度不足，需要至少 {cls.HEADER_SIZE} 字节")

        # 解包
        magic_code, data_type, length, checksum = struct.unpack(
            cls.HEADER_FORMAT,
            data[:cls.HEADER_SIZE]
        )

        # 验证魔数
        if magic_code != MAGIC_CODE:
            raise ValueError(f"无效的魔数: 0x{magic_code:04X}, 期望: 0x{MAGIC_CODE:04X}")

        return cls(
            magic_code=magic_code,
            data_type=data_type,
            length=length,
            checksum=checksum
        )

    def to_bytes(self) -> bytes:
        """
        将包头序列化为字节流

        Returns:
            10 字节的包头数据
        """
        return struct.pack(
            self.HEADER_FORMAT,
            self.magic_code,
            self.data_type,
            self.length,
            self.checksum
        )

    def validate(self, data: bytes) -> bool:
        """
        验证数据完整性（使用 CRC16）

        Args:
            data: 要验证的数据

        Returns:
            数据是否完整
        """
        return self.checksum == calculate_crc16(data)


class AEPacket(BaseModel):
    """
    完整的数据包

    包含包头和数据
    """
    header: AEPacketHeader
    data: bytes

    @classmethod
    def create(cls, data_type: AEDataType, data: bytes) -> 'AEPacket':
        """
        创建数据包

        Args:
            data_type: 数据类型
            data: 数据内容

        Returns:
            完整的数据包对象
        """
        # 计算校验和（CRC16）
        checksum = calculate_crc16(data)

        # 创建包头
        header = AEPacketHeader(
            data_type=data_type.value,
            length=len(data),
            checksum=checksum
        )

        return cls(header=header, data=data)

    def to_bytes(self) -> bytes:
        """
        将数据包序列化为字节流

        Returns:
            完整的数据包字节流
        """
        return self.header.to_bytes() + self.data

    @classmethod
    def from_bytes(cls, header: AEPacketHeader, data: bytes) -> 'AEPacket':
        """
        从包头和数据创建数据包

        Args:
            header: 已解析的包头
            data: 数据内容

        Returns:
            数据包对象

        Raises:
            ValueError: 如果校验失败
        """
        # 验证数据完整性
        if not header.validate(data):
            actual_crc = calculate_crc16(data)
            raise ValueError(f"数据校验失败: 期望 0x{header.checksum:04X}, 实际 0x{actual_crc:04X}")

        return cls(header=header, data=data)

    model_config = {"arbitrary_types_allowed": True}


def calculate_crc16(data: bytes) -> int:
    """
    计算数据的 CRC16 校验和（CRC-16/MODBUS）

    Args:
        data: 要计算校验和的数据

    Returns:
        CRC16 校验和（0x0000 - 0xFFFF）
    """
    crc = 0xFFFF

    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1

    return crc & 0xFFFF


def calculate_checksum(data: bytes) -> int:
    """
    计算数据的校验和（别名，使用 CRC16）

    Args:
        data: 要计算校验和的数据

    Returns:
        CRC16 校验和
    """
    return calculate_crc16(data)
