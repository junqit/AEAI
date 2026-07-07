"""
AEPacketPool - 单条消息的分片收集与拼装。

同一 UniqueID 的多个分片归入同一个 AEPacketPool：
- add(packet) 追加一个分片；已收到末包（FLAG_LAST_FRAGMENT）且 0..last_seq 全部到齐时组包，
  组包完成后清空 _packets。
- is_complete() 检测是否已组包完成：_packets 为空代表包已经完整。
- assemble() 返回组包后的完整数据。
"""
from typing import Dict, Optional

from .AEPacket import AEPacket, FLAG_LAST_FRAGMENT


class AEPacketPool:
    """一条消息的分片池：按 unique_id 聚合分片，组包并清空，_packets 为空代表已完整。"""

    def __init__(self, unique_id: int, packet: AEPacket):
        self.unique_id: int = unique_id
        # seq -> packet，便于按序拼装与去重；组包完成后清空
        self._packets: Dict[int, AEPacket] = {}
        # 末包 seq；未收到末包时为 None
        self._last_seq: Optional[int] = None
        # 组包后的完整数据；未组包完成时为 None
        self._assembled: Optional[bytes] = None
        # 分片数据类型（低 4 位），组包清空 _packets 后仍保留供外部读取
        self._data_type_value: int = 0
        # 传入收到的第一个分片
        self.add(packet)

    @property
    def last_seq(self) -> Optional[int]:
        """末包 seq；未收到末包时为 None。"""
        return self._last_seq

    @property
    def data_type_value(self) -> int:
        """分片数据类型（低 4 位）。同一消息各分片类型一致。"""
        return self._data_type_value

    def add(self, packet: AEPacket) -> None:
        """追加一个分片；已收到末包且收齐时组包，组包后清空 _packets。"""
        seq = packet.header.packet_seq
        self._packets[seq] = packet
        self._data_type_value = packet.header.data_type_value
        if packet.header.data_type & FLAG_LAST_FRAGMENT:
            self._last_seq = seq

        # 末包已到且 0..last_seq 全部到齐 → 组包
        if self._last_seq is not None and all(
            i in self._packets for i in range(self._last_seq + 1)
        ):
            self._assembled = b"".join(
                self._packets[i].data for i in range(self._last_seq + 1)
            )
            # 组包完成，清空 _packets（为空代表已完整）
            self._packets.clear()

    def is_complete(self) -> bool:
        """是否已组包完成：_packets 为空代表包已经完整。"""
        return len(self._packets) == 0

    def assemble(self) -> bytes:
        """返回组包后的完整数据；未组包完成时返回空 bytes。"""
        return self._assembled or b""
