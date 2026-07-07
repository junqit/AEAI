"""
网络数据包协议定义

包结构：
┌─────────────┬──────────┬───────────┬──────────┬──────────┬──────────┬──────────┐
│ Magic Code  │ DataType │ UniqueID  │ PacketSeq│  Length  │ Checksum │   Data   │
│   (2 bytes) │ (1 byte) │ (2 bytes) │ (1 byte) │ (2 bytes)│ (2 bytes)│ (N bytes)│
└─────────────┴──────────┴───────────┴──────────┴──────────┴──────────┴──────────┘

总包头长度: 10 bytes
- Magic Code (2 bytes)：魔数 0x1EAE
- DataType   (1 byte) ：数据类型（AEDataType）
- UniqueID   (2 bytes)：唯一标识，同一消息的多个分片共用
- PacketSeq  (1 byte) ：包次（分片序号，从 0 开始）
- Length     (2 bytes)：本包数据长度（分片后单个包的 Data 长度）
- Checksum   (2 bytes)：本包 Data 的 CRC16 校验和
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

# 2 字节无符号最值
MIN_UINT16 = 0x0000
MAX_UINT16 = 0xFFFF

# 单包 Data 最大长度：2 字节上限 0xFFFF 扣除 UDP 头(8) + AEPacket 包头(10)
# 该值 0xFFED 的二进制第 4 位（0x10）为 0
MAX_PACKET_DATA_LENGTH = 4 * 1024
LAST_PACKET_MASK = 0xFFFD

# UniqueID 哨兵值：0 表示非分片单包（无唯一标识需求）
UNIQUE_ID_SENTINEL = MIN_UINT16


class AEDataType(Enum):
    """数据类型枚举

    DataType 字节低 4 位表示数据类型（取值 0x0~0xF），高 4 位保留（可用于标志位）。
    解析时用 DATA_TYPE_MASK 取低 4 位再匹配枚举。
    """
    REQUEST = 0x01    # 请求数据 (AENetReq)
    RESPONSE = 0x02   # 响应数据 (AENetRsp)
    HEARTBEAT = 0x03  # 心跳包
    PING = 0x04       # Ping
    PONG = 0x05       # Pong
    CUSTOM = 0x0F     # 自定义数据


# DataType 字节低 4 位为数据类型，高 4 位为标志位
DATA_TYPE_MASK = 0x0F
# 末包标志：第 4 位（0x10）。将该位置 1、其余位不变，表示该分片已是最后一包
# 用法：末包 data_type = 类型值 | FLAG_LAST_FRAGMENT（如 RESPONSE 末包 = 0x02 | 0x10 = 0x12）
FLAG_LAST_FRAGMENT = 0x10


class AEPacketHeader(BaseModel):
    """
    数据包头结构

    字段说明：
    - magic_code:  魔数，固定为 0x1EAE，2 字节
    - data_type:   数据类型（AEDataType），1 字节
    - unique_id:   唯一标识，同一消息的多个分片共用；0 (UNIQUE_ID_SENTINEL) 表示非分片单包，2 字节
    - packet_seq:  包次（分片序号，从 0 开始），1 字节
    - length:      本包数据长度（不包含包头），2 字节
    - checksum:    数据校验和（CRC16），2 字节
    """
    magic_code: int = MAGIC_CODE
    data_type: int  # AEDataType
    unique_id: int = UNIQUE_ID_SENTINEL
    packet_seq: int = 0
    length: int
    checksum: int

    HEADER_SIZE: ClassVar[int] = 10  # 2 + 1 + 2 + 1 + 2 + 2
    # ! = 网络字节序(大端)；H=2 B=1 H=2 B=1 H=2 H=2
    HEADER_FORMAT: ClassVar[str] = '!HBHBHH'

    @classmethod
    def from_bytes(cls, data: bytes) -> 'AEPacketHeader':
        if len(data) < cls.HEADER_SIZE:
            raise ValueError(f"数据长度不足，需要至少 {cls.HEADER_SIZE} 字节")

        magic_code, data_type, unique_id, packet_seq, length, checksum = struct.unpack(
            cls.HEADER_FORMAT,
            data[:cls.HEADER_SIZE]
        )

        if magic_code != MAGIC_CODE:
            raise ValueError(f"无效的魔数: 0x{magic_code:04X}, 期望: 0x{MAGIC_CODE:04X}")

        return cls(
            magic_code=magic_code,
            data_type=data_type,
            unique_id=unique_id,
            packet_seq=packet_seq,
            length=length,
            checksum=checksum
        )

    def to_bytes(self) -> bytes:
        return struct.pack(
            self.HEADER_FORMAT,
            self.magic_code,
            self.data_type,
            self.unique_id,
            self.packet_seq,
            self.length,
            self.checksum
        )

    def validate(self, data: bytes) -> bool:
        return self.checksum == calculate_crc16(data)

    @property
    def data_type_value(self) -> int:
        """取 DataType 低 4 位（实际数据类型，高 4 位为保留标志位）。"""
        return self.data_type & DATA_TYPE_MASK


class AEPacket(BaseModel):
    """完整的数据包"""
    header: AEPacketHeader
    data: bytes

    @classmethod
    def create(
        cls,
        data_type: AEDataType,
        data: bytes,
        unique_id: int = UNIQUE_ID_SENTINEL,
        packet_seq: int = 0,
        is_last_fragment: bool = False,
    ) -> 'AEPacket':
        # 末包：第 4 位置 1，其余位（类型位）不变
        raw_data_type = (data_type.value | FLAG_LAST_FRAGMENT) if is_last_fragment else data_type.value
        checksum = calculate_crc16(data)
        header = AEPacketHeader(
            data_type=raw_data_type,
            unique_id=unique_id,
            packet_seq=packet_seq,
            length=len(data),
            checksum=checksum
        )
        return cls(header=header, data=data)

    # 分片 UniqueID 自增序号（类级共享，跳过 0 哨兵值）
    # 用 ClassVar 声明，避免被 Pydantic 当作 ModelPrivateAttr
    _unique_id_seq: ClassVar[int] = 0

    @classmethod
    def _next_unique_id(cls) -> int:
        """生成下一个分片 UniqueID（1..MAX_UINT16，跳过 0 哨兵值）。"""
        cls._unique_id_seq = (cls._unique_id_seq + 1) % (MAX_UINT16 + 1)
        if cls._unique_id_seq == UNIQUE_ID_SENTINEL:
            cls._unique_id_seq = 1
        return cls._unique_id_seq

    @classmethod
    def packets_from_data(
        cls,
        data_type: AEDataType,
        data: bytes,
    ) -> list:
        """由 data 转换为 AEPacket 列表（单包或分片），内聚处理 UniqueID 与末包标志。

        - data <= MAX_PACKET_DATA_LENGTH：单包，UniqueID 用哨兵值（接收侧直接分发，不进分片池）
        - data >  MAX_PACKET_DATA_LENGTH：分片，共用一个非哨兵 UniqueID，packet_seq 从 0 递增，
          末包 data_type 第 4 位置 1（FLAG_LAST_FRAGMENT）

        Args:
            data_type: 数据类型
            data: 待发送的完整数据

        Returns:
            List[AEPacket]: packet 列表（按发送顺序）
        """
        packets = []

        # 单包：无需分片，UniqueID 用哨兵值
        if len(data) <= MAX_PACKET_DATA_LENGTH:
            packets.append(cls.create(data_type, data))
            return packets

        # 分片：共用 UniqueID，末包打标志
        unique_id = cls._next_unique_id()
        total = (len(data) + MAX_PACKET_DATA_LENGTH - 1) // MAX_PACKET_DATA_LENGTH
        for seq in range(total):
            chunk = data[seq * MAX_PACKET_DATA_LENGTH:(seq + 1) * MAX_PACKET_DATA_LENGTH]
            packets.append(cls.create(
                data_type,
                chunk,
                unique_id=unique_id,
                packet_seq=seq,
                is_last_fragment=(seq == total - 1),
            ))
        return packets

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
