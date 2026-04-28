"""网络数据模型单元测试"""

import unittest
from AEIQ.Network.Core import AENetReq, AENetRsp, AENetErrorInfo


class TestAENetReq(unittest.TestCase):
    """测试 AENetReq"""

    def test_create_request(self):
        req = AENetReq(
            action="chat",
            context={"id": "ctx_001"},
            requestId="req_001"
        )
        self.assertEqual(req.action, "chat")
        self.assertEqual(req.requestId, "req_001")

    def test_serialize_deserialize(self):
        req = AENetReq(
            action="chat",
            context={"id": "ctx_001"},
            question={"type": "text", "content": "Hello"},
            requestId="req_001"
        )
        bytes_data = req.to_bytes()
        req_restored = AENetReq.from_bytes(bytes_data)
        self.assertEqual(req_restored.action, req.action)
        self.assertEqual(req_restored.requestId, req.requestId)


class TestAENetRsp(unittest.TestCase):
    """测试 AENetRsp"""

    def test_create_success_response(self):
        rsp = AENetRsp.create_success(
            content="Success",
            result={"key": "value"},
            request_id="req_001"
        )
        self.assertEqual(rsp.status, "success")

    def test_create_error_response(self):
        rsp = AENetRsp.create_error(
            error_code="ERR_001",
            error_message="Error occurred",
            request_id="req_001"
        )
        self.assertEqual(rsp.status, "error")
        self.assertEqual(rsp.error.code, "ERR_001")

    def test_serialize_deserialize(self):
        rsp = AENetRsp.create_success(
            content="Test",
            result={"key": "value"},
            request_id="req_001"
        )
        bytes_data = rsp.to_bytes()
        rsp_restored = AENetRsp.from_bytes(bytes_data)
        self.assertEqual(rsp_restored.status, rsp.status)
        self.assertEqual(rsp_restored.content, rsp.content)


if __name__ == '__main__':
    unittest.main()

