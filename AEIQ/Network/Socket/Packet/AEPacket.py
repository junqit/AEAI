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
    - magic_code: 魔数，固定为 0x1EAE，2字节
    - data_type: 数据类型，2字节
    - length: 数据长度（不包含包头），4字节
    - checksum: 数据校验和（CRC16），2字节
    """
    magic_code: int = MAGIC_CODE
    data_type: int  # AEDataType
    length: int
    checksum: int

    HEADER_SIZE: ClassVar[int] = 10  # 2 + 2 + 4 + 2
    HEADER_FORMAT: ClassVar[str] = '!HHIH'  # ! = 网络字节序(大端)

    @classmethod
    def from_bytes(cls, data: bytes) -> 'AEPacketHeader':
        if len(data) < cls.HEADER_SIZE:
            raise ValueError(f"数据长度不足，需要至少 {cls.HEADER_SIZE} 字节")

        magic_code, data_type, length, checksum = struct.unpack(
            cls.HEADER_FORMAT,
            data[:cls.HEADER_SIZE]
        )

        if magic_code != MAGIC_CODE:
            raise ValueError(f"无效的魔数: 0x{magic_code:04X}, 期望: 0x{MAGIC_CODE:04X}")

        return cls(
            magic_code=magic_code,
            data_type=data_type,
            length=length,
            checksum=checksum
        )

    def to_bytes(self) -> bytes:
        return struct.pack(
            self.HEADER_FORMAT,
            self.magic_code,
            self.data_type,
            self.length,
            self.checksum
        )

    def validate(self, data: bytes) -> bool:
        return self.checksum == calculate_crc16(data)


class AEPacket(BaseModel):
    """完整的数据包"""
    header: AEPacketHeader
    data: bytes

    @classmethod
    def create(cls, data_type: AEDataType, data: bytes) -> 'AEPacket':
        checksum = calculate_crc16(data)
        header = AEPacketHeader(
            data_type=data_type.value,
            length=len(data),
            checksum=checksum
        )
        return cls(header=header, data=data)

    def to_bytes(self) -> bytes:
        return self.header.to_bytes() + self.data

    @classmethod
    def from_bytes(cls, header: AEPacketHeader, data: bytes) -> 'AEPacket':
        if not header.validate(data):
            actual_crc = calculate_crc16(data)
            raise ValueError(f"数据校验失败: 期望 0x{header.checksum:04X}, 实际 0x{actual_crc:04X}")
        return cls(header=header, data=data)

    model_config = {"arbitrary_types_allowed": True}


def calculate_crc16(data: bytes) -> int:
    """计算数据的 CRC16 校验和（CRC-16/MODBUS）"""
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
    """计算数据的校验和（别名，使用 CRC16）"""
    return calculate_crc16(data)
