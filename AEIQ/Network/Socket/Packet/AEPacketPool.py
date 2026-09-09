"""
AEPacketPool - 单条消息的分片收集与拼装。对标 Swift AEPacketPool。

同一 UniqueID 的多个分片归入同一个 AEPacketPool：
- add(packet) 追加一个分片；末包（packetSeq == LAST_PACKET_SEQ）已到且
  firstSeq..lastSeq 全部到齐（数量 == lastSeq - firstSeq + 1）时组包，组包完成后清空 _packets。
- is_complete() 检测是否已组包完成：_packets 为空代表包已经完整。
- assemble() 返回组包后的完整数据。
"""
from typing import Dict, Optional

from .AEPacket import AEPacket


class AEPacketPool:
    """一条消息的分片池：按 unique_id 聚合分片，组包并清空，_packets 为空代表已完整。"""

    def __init__(self, unique_id: int, packet: AEPacket):
        self.unique_id: int = unique_id
        # seq -> packet，便于按序拼装与去重；组包完成后清空
        self._packets: Dict[int, AEPacket] = {}
        # 首包 seq（首个收到的分片；有序到达即最小 seq）
        self._first_seq: Optional[int] = None
        # 末包 seq（== LAST_PACKET_SEQ）；未收到末包时为 None
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
        """追加一个分片；末包已到且收齐时组包，组包后清空 _packets。"""
        seq = packet.header.packet_seq
        self._packets[seq] = packet
        self._data_type_value = packet.header.data_type_value

        # 首包 seq 仅在首个分片到达时记录（有序到达即最小 seq）
        if self._first_seq is None:
            self._first_seq = seq

        # 末包：packetSeq == LAST_PACKET_SEQ(255)
        if packet.header.is_last_fragment:
            self._last_seq = seq

        # 末包已到且 收到数量 == lastSeq - firstSeq + 1（跨度等于数量，无空洞）→ 组包
        if self._first_seq is not None and self._last_seq is not None:
            span = self._last_seq - self._first_seq + 1
            if len(self._packets) == span:
                self._assembled = b"".join(
                    self._packets[self._first_seq + i].data for i in range(span)
                )
                # 组包完成，清空 _packets（为空代表已完整）
                self._packets.clear()

    def is_complete(self) -> bool:
        """是否已组包完成：_packets 为空代表包已经完整。"""
        return len(self._packets) == 0

    def assemble(self) -> bytes:
        """返回组包后的完整数据；未组包完成时返回空 bytes。"""
        return self._assembled or b""
