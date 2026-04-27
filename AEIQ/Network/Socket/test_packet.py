"""
测试新的包头结构和数据解析
"""

import unittest
from AEIQ.Network.Socket import AEPacket, AEPacketHeader, AEDataType, MAGIC_CODE
from AEIQ.Network.Socket.AEReceiveBuffer import AEReceiveBuffer
from AEIQ.Network.Core import AENetReq, AENetReqAction, AENetReqData


class TestAEPacketHeader(unittest.TestCase):
    """测试数据包头"""

    def test_create_header(self):
        """测试创建包头"""
        header = AEPacketHeader(
            data_type=AEDataType.REQUEST.value,
            length=100,
            checksum=0x1234  # 使用2字节范围内的值
        )
        self.assertEqual(header.magic_code, MAGIC_CODE)
        self.assertEqual(header.data_type, AEDataType.REQUEST.value)
        self.assertEqual(header.length, 100)

    def test_header_serialization(self):
        """测试包头序列化"""
        header = AEPacketHeader(
            data_type=AEDataType.RESPONSE.value,
            length=200,
            checksum=0xABCD  # 使用2字节范围内的值
        )

        # 序列化
        header_bytes = header.to_bytes()
        self.assertEqual(len(header_bytes), AEPacketHeader.HEADER_SIZE)

        # 反序列化
        header_restored = AEPacketHeader.from_bytes(header_bytes)
        self.assertEqual(header_restored.magic_code, header.magic_code)
        self.assertEqual(header_restored.data_type, header.data_type)
        self.assertEqual(header_restored.length, header.length)
        self.assertEqual(header_restored.checksum, header.checksum)

    def test_invalid_magic_code(self):
        """测试无效魔数"""
        # 构造一个错误的包头（10字节）
        invalid_bytes = b'\x00\x00' + b'\x00' * 8

        with self.assertRaises(ValueError) as context:
            AEPacketHeader.from_bytes(invalid_bytes)

        self.assertIn("无效的魔数", str(context.exception))


class TestAEPacket(unittest.TestCase):
    """测试完整数据包"""

    def test_create_packet(self):
        """测试创建数据包"""
        data = b'Hello, World!'
        packet = AEPacket.create(AEDataType.REQUEST, data)

        self.assertEqual(packet.header.data_type, AEDataType.REQUEST.value)
        self.assertEqual(packet.header.length, len(data))
        self.assertEqual(packet.data, data)

    def test_packet_serialization(self):
        """测试数据包序列化"""
        data = b'Test Data'
        packet = AEPacket.create(AEDataType.RESPONSE, data)

        # 序列化
        packet_bytes = packet.to_bytes()
        self.assertGreater(len(packet_bytes), AEPacketHeader.HEADER_SIZE)

        # 反序列化
        header = AEPacketHeader.from_bytes(packet_bytes)
        data_start = AEPacketHeader.HEADER_SIZE
        data_end = data_start + header.length
        packet_data = packet_bytes[data_start:data_end]

        packet_restored = AEPacket.from_bytes(header, packet_data)
        self.assertEqual(packet_restored.data, data)

    def test_packet_checksum_validation(self):
        """测试数据包校验"""
        data = b'Valid Data'
        packet = AEPacket.create(AEDataType.REQUEST, data)

        # 正确的数据应该验证通过
        self.assertTrue(packet.header.validate(packet.data))

        # 修改数据后应该验证失败
        corrupted_data = b'Invalid Data'
        self.assertFalse(packet.header.validate(corrupted_data))

    def test_packet_with_request(self):
        """测试包含 AENetReq 的数据包"""
        # 创建请求
        request = AENetReq(
            action=AENetReqAction.CHAT,
            data=AENetReqData(content="test"),
            request_id="req_001"
        )

        # 序列化请求
        request_json = request.model_dump_json().encode('utf-8')

        # 创建数据包
        packet = AEPacket.create(AEDataType.REQUEST, request_json)

        # 序列化数据包
        packet_bytes = packet.to_bytes()

        # 反序列化数据包
        header = AEPacketHeader.from_bytes(packet_bytes)
        data = packet_bytes[AEPacketHeader.HEADER_SIZE:AEPacketHeader.HEADER_SIZE + header.length]
        packet_restored = AEPacket.from_bytes(header, data)

        # 反序列化请求
        request_restored = AENetReq.from_bytes(packet_restored.data)
        self.assertEqual(request_restored.action, request.action)
        self.assertEqual(request_restored.request_id, request.request_id)


class TestAEReceiveBuffer(unittest.TestCase):
    """测试接收缓冲区"""

    def test_buffer_append(self):
        """测试追加数据"""
        buffer = AEReceiveBuffer()
        data = b'Hello'
        buffer.append(data)
        self.assertEqual(buffer.size, len(data))

    def test_buffer_overflow(self):
        """测试缓冲区溢出"""
        buffer = AEReceiveBuffer(max_buffer_size=100)

        # 追加超过限制的数据
        with self.assertRaises(OverflowError):
            buffer.append(b'x' * 101)

    def test_parse_complete_packet(self):
        """测试解析完整数据包"""
        # 创建一个完整的数据包
        data = b'Test Message'
        packet = AEPacket.create(AEDataType.REQUEST, data)
        packet_bytes = packet.to_bytes()

        # 添加到缓冲区
        buffer = AEReceiveBuffer()
        buffer.append(packet_bytes)

        # 尝试解析
        parsed_packet = buffer.try_parse_packet()
        self.assertIsNotNone(parsed_packet)
        self.assertEqual(parsed_packet.data, data)

        # 缓冲区应该为空
        self.assertEqual(buffer.size, 0)

    def test_parse_incomplete_packet(self):
        """测试解析不完整数据包"""
        # 创建一个完整的数据包
        data = b'Test Message'
        packet = AEPacket.create(AEDataType.REQUEST, data)
        packet_bytes = packet.to_bytes()

        # 只添加一半数据
        buffer = AEReceiveBuffer()
        buffer.append(packet_bytes[:10])

        # 尝试解析，应该返回 None
        parsed_packet = buffer.try_parse_packet()
        self.assertIsNone(parsed_packet)

        # 缓冲区应该保留数据
        self.assertEqual(buffer.size, 10)

    def test_parse_multiple_packets(self):
        """测试解析多个数据包（粘包）"""
        # 创建两个数据包
        packet1 = AEPacket.create(AEDataType.REQUEST, b'Message 1')
        packet2 = AEPacket.create(AEDataType.RESPONSE, b'Message 2')

        # 合并发送（模拟粘包）
        combined = packet1.to_bytes() + packet2.to_bytes()

        # 添加到缓冲区
        buffer = AEReceiveBuffer()
        buffer.append(combined)

        # 解析第一个包
        parsed1 = buffer.try_parse_packet()
        self.assertIsNotNone(parsed1)
        self.assertEqual(parsed1.data, b'Message 1')

        # 解析第二个包
        parsed2 = buffer.try_parse_packet()
        self.assertIsNotNone(parsed2)
        self.assertEqual(parsed2.data, b'Message 2')

        # 缓冲区应该为空
        self.assertEqual(buffer.size, 0)

    def test_parse_with_partial_data(self):
        """测试分批接收数据（半包）"""
        # 创建一个数据包
        packet = AEPacket.create(AEDataType.REQUEST, b'Test Message')
        packet_bytes = packet.to_bytes()

        buffer = AEReceiveBuffer()

        # 分三次接收
        chunk_size = len(packet_bytes) // 3

        # 第一次接收
        buffer.append(packet_bytes[:chunk_size])
        self.assertIsNone(buffer.try_parse_packet())

        # 第二次接收
        buffer.append(packet_bytes[chunk_size:chunk_size*2])
        self.assertIsNone(buffer.try_parse_packet())

        # 第三次接收
        buffer.append(packet_bytes[chunk_size*2:])
        parsed = buffer.try_parse_packet()
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.data, b'Test Message')


class TestDataTypes(unittest.TestCase):
    """测试数据类型"""

    def test_all_data_types(self):
        """测试所有数据类型"""
        for dtype in AEDataType:
            packet = AEPacket.create(dtype, b'test')
            self.assertEqual(packet.header.data_type, dtype.value)


if __name__ == '__main__':
    unittest.main()
