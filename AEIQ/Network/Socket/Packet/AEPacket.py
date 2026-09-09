"""
网络数据包协议定义

包结构：
┌─────────────┬──────────┬───────────┬──────────┬──────────┬──────────┬──────────┐
│ Magic Code  │ DataType │ UniqueID  │ PacketSeq│  Length  │ Checksum │   Data   │
│   (2 bytes) │ (1 byte) │ (2 bytes) │ (1 byte) │ (2 bytes)│ (2 bytes)│ (N bytes)│
└─────────────┴──────────┴───────────┴──────────┴──────────┴──────────┴──────────┘

总包头长度: 10 bytes
- Magic Code (2 bytes)：魔数 0x1EAE
- DataType   (1 byte) ：低 4 位数据类型（AEDataType），高 4 位标志位（AEFlag）
- UniqueID   (2 bytes)：唯一标识，同一消息的多个分片共用；0 (UNIQUE_ID_SENTINEL) 表示非分片单包
- PacketSeq  (1 byte) ：包次（分片序号）；分片从 (LAST_PACKET_SEQ-total+1) 递增至 LAST_PACKET_SEQ(255)，末包恒为 255
- Length     (2 bytes)：本包数据长度（分片后单个包的 Data 长度）
- Checksum   (2 bytes)：本包 Data 的 CRC16 校验和

对标 Client/CocoaPods/AENetworkEngine 的 AEPacket 协议。
"""

from enum import Enum
from typing import ClassVar
from pydantic import BaseModel
import struct


# 魔数：0x1E = ASCII Record Separator (RS)，0xAE = 扩展 ASCII；正常文本/JSON 中不会出现
MAGIC_CODE = 0x1EAE

# 2 字节无符号最值
MIN_UINT16 = 0x0000
MAX_UINT16 = 0xFFFF

# 单包 Data 最大长度
MAX_PACKET_DATA_LENGTH = 4 * 1024

# 末包分片序号：分片 packetSeq 从 (LAST_PACKET_SEQ-total+1) 递增至 255，末包恒为 255
# 接收侧据此判定末包（不再使用标志位）
LAST_PACKET_SEQ = 0xFF  # 255

# UniqueID 哨兵值：0 表示非分片单包（无唯一标识需求）
UNIQUE_ID_SENTINEL = MIN_UINT16

# DataType 字节低 4 位为数据类型，高 4 位为标志位
DATA_TYPE_MASK = 0x0F


class AEDataType(Enum):
    """数据类型（DataType 字节低 4 位）。对标 Swift AEDataType。"""
    DATA = 0x00          # 业务数据（AENetReq / AENetRsp，按 JSON req.headers.type 区分）
    HEARTBEAT = 0x01     # 心跳包
    PING = 0x02          # Ping
    PONG = 0x03          # Pong


class AEFlag:
    """标志位（DataType 字节高 4 位）。对标 Swift AEFlag；多个标志位可按位或。"""
    COMPRESSED = 0x20   # 压缩
    ENCRYPTED = 0x40      # 加密
    RESERVED = 0x80       # 保留


class AEPacketHeader(BaseModel):
    """数据包头结构（10 bytes，大端序）"""
    magic_code: int = MAGIC_CODE
    data_type: int          # 低 4 位类型 | 高 4 位标志位
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
            cls.HEADER_FORMAT, data[:cls.HEADER_SIZE]
        )
        if magic_code != MAGIC_CODE:
            raise ValueError(f"无效的魔数: 0x{magic_code:04X}, 期望: 0x{MAGIC_CODE:04X}")
        return cls(magic_code=magic_code, data_type=data_type, unique_id=unique_id,
                   packet_seq=packet_seq, length=length, checksum=checksum)

    def to_bytes(self) -> bytes:
        return struct.pack(self.HEADER_FORMAT, self.magic_code, self.data_type,
                           self.unique_id, self.packet_seq, self.length, self.checksum)

    def validate(self, data: bytes) -> bool:
        return self.checksum == calculate_crc16(data)

    @property
    def data_type_value(self) -> int:
        """取 DataType 低 4 位（实际数据类型）。"""
        return self.data_type & DATA_TYPE_MASK

    @property
    def flags(self) -> int:
        """取 DataType 高 4 位（标志位）。"""
        return self.data_type & 0xF0

    @property
    def is_compressed(self) -> bool:
        return (self.flags & AEFlag.COMPRESSED) != 0

    @property
    def is_encrypted(self) -> bool:
        return (self.flags & AEFlag.ENCRYPTED) != 0

    @property
    def is_last_fragment(self) -> bool:
        """末包：packetSeq == LAST_PACKET_SEQ(255)。对标 Swift isLastFragment。"""
        return self.packet_seq == LAST_PACKET_SEQ

    @property
    def is_single_packet(self) -> bool:
        return self.unique_id == UNIQUE_ID_SENTINEL


class AEPacket(BaseModel):
    """完整的数据包"""
    header: AEPacketHeader
    data: bytes

    @classmethod
    def create(cls, data_type: AEDataType, data: bytes,
               unique_id: int = UNIQUE_ID_SENTINEL, packet_seq: int = 0) -> 'AEPacket':
        # 末包由 packetSeq == LAST_PACKET_SEQ 判定，不再使用标志位；flags 高 4 位默认 0
        checksum = calculate_crc16(data)
        header = AEPacketHeader(
            data_type=data_type.value,
            unique_id=unique_id,
            packet_seq=packet_seq,
            length=len(data),
            checksum=checksum,
        )
        return cls(header=header, data=data)

    # 分片 UniqueID 自增序号（类级共享，跳过 0 哨兵值）
    _unique_id_seq: ClassVar[int] = 0

    @classmethod
    def _next_unique_id(cls) -> int:
        """生成下一个分片 UniqueID（1..MAX_UINT16，跳过 0 哨兵值）。"""
        cls._unique_id_seq = (cls._unique_id_seq + 1) % (MAX_UINT16 + 1)
        if cls._unique_id_seq == UNIQUE_ID_SENTINEL:
            cls._unique_id_seq = 1
        return cls._unique_id_seq

    @classmethod
    def packets_from_data(cls, data_type: AEDataType, data: bytes) -> list:
        """由 data 构造 packet 列表（单包或分片），对标 Swift AEPackageData.makePackets。

        - data <= MAX_PACKET_DATA_LENGTH：单包，UniqueID 用哨兵值（接收侧直接分发，不进分片池）
        - data >  MAX_PACKET_DATA_LENGTH：分片，共用一个非哨兵 UniqueID，packetSeq 从
          (LAST_PACKET_SEQ-total+1) 递增至 LAST_PACKET_SEQ(255)，末包恒为 255
        """
        packets = []
        if len(data) <= MAX_PACKET_DATA_LENGTH:
            packets.append(cls.create(data_type, data))
            return packets

        unique_id = cls._next_unique_id()
        total = (len(data) + MAX_PACKET_DATA_LENGTH - 1) // MAX_PACKET_DATA_LENGTH
        # 分片数不可超过 LAST_PACKET_SEQ（末包恒为 255，倒数下溢即超限）
        if total > LAST_PACKET_SEQ:
            return []

        for i in range(total):
            chunk = data[i * MAX_PACKET_DATA_LENGTH:(i + 1) * MAX_PACKET_DATA_LENGTH]
            # seq 从 (LAST_PACKET_SEQ-total+1) 递增至 LAST_PACKET_SEQ，末包恒为 255
            seq = LAST_PACKET_SEQ - total + 1 + i
            packets.append(cls.create(data_type, chunk, unique_id=unique_id, packet_seq=seq))
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
