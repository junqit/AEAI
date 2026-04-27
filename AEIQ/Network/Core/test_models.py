"""
更新后的网络数据模型单元测试
"""

import unittest
from AEIQ.Network.Core import (
    AENetReq, AENetReqAction, AENetReqData,
    AENetRsp, AENetRspStatus, AENetErrorInfo, AENetRspData
)


class TestAENetReq(unittest.TestCase):
    """测试 AENetReq"""

    def test_create_with_enum(self):
        """测试使用枚举创建请求"""
        req = AENetReq(
            action=AENetReqAction.CHAT,
            data=AENetReqData(content="test"),
            request_id="req_001"
        )
        self.assertEqual(req.action, AENetReqAction.CHAT.value)
        self.assertEqual(req.request_id, "req_001")

    def test_create_with_string(self):
        """测试使用字符串创建请求（通过 JSON）"""
        json_str = '{"action": "query", "data": null, "request_id": "req_002"}'
        req = AENetReq.model_validate_json(json_str)
        self.assertEqual(req.action, AENetReqAction.QUERY.value)

    def test_enum_to_value(self):
        """测试枚举自动转换为值"""
        req = AENetReq(action=AENetReqAction.COMMAND)
        data = req.model_dump()
        # 因为 use_enum_values = True，枚举会转换为字符串
        self.assertEqual(data['action'], 'command')

    def test_serialize_deserialize(self):
        """测试序列化和反序列化"""
        req = AENetReq(
            action=AENetReqAction.CHAT,
            data=AENetReqData(
                content="Hello",
                parameters={"key": "value"}
            ),
            request_id="req_001"
        )

        # 序列化
        bytes_data = req.to_bytes()
        self.assertIsInstance(bytes_data, bytes)
        self.assertGreater(len(bytes_data), 4)

        # 反序列化（跳过前4字节长度）
        req_restored = AENetReq.from_bytes(bytes_data[4:])
        self.assertEqual(req_restored.action, req.action)
        self.assertEqual(req_restored.request_id, req.request_id)
        if req.data:
            self.assertEqual(req_restored.data.content, req.data.content)

    def test_all_actions(self):
        """测试所有动作类型"""
        for action in AENetReqAction:
            req = AENetReq(action=action)
            self.assertEqual(req.action, action.value)


class TestAENetRsp(unittest.TestCase):
    """测试 AENetRsp"""

    def test_create_success_response(self):
        """测试创建成功响应"""
        rsp = AENetRsp(
            status=AENetRspStatus.SUCCESS,
            data=AENetRspData(
                content="Success",
                result={"key": "value"}
            ),
            request_id="req_001"
        )
        self.assertEqual(rsp.status, AENetRspStatus.SUCCESS.value)
        self.assertTrue(rsp.is_success)
        self.assertFalse(rsp.is_error)

    def test_create_error_response(self):
        """测试创建错误响应"""
        rsp = AENetRsp(
            status=AENetRspStatus.ERROR,
            error=AENetErrorInfo(
                code="ERR_001",
                message="Error occurred"
            ),
            request_id="req_001"
        )
        self.assertEqual(rsp.status, AENetRspStatus.ERROR.value)
        self.assertFalse(rsp.is_success)
        self.assertTrue(rsp.is_error)

    def test_success_helper(self):
        """测试成功响应快捷方法"""
        rsp = AENetRsp.create_success(
            data=AENetRspData(content="OK"),
            request_id="req_001"
        )
        self.assertEqual(rsp.status, AENetRspStatus.SUCCESS.value)
        self.assertTrue(rsp.is_success)

    def test_error_helper(self):
        """测试错误响应快捷方法"""
        rsp = AENetRsp.create_error(
            error_code="ERR_001",
            error_message="Test error",
            error_details={"detail": "info"},
            request_id="req_001"
        )
        self.assertEqual(rsp.status, AENetRspStatus.ERROR.value)
        self.assertTrue(rsp.is_error)
        self.assertEqual(rsp.error.code, "ERR_001")
        self.assertEqual(rsp.error.message, "Test error")

    def test_serialize_deserialize(self):
        """测试序列化和反序列化"""
        rsp = AENetRsp.create_success(
            data=AENetRspData(
                content="Test",
                result={"key": "value"}
            ),
            request_id="req_001"
        )

        # 序列化
        bytes_data = rsp.to_bytes()
        self.assertIsInstance(bytes_data, bytes)

        # 反序列化（跳过前4字节长度）
        rsp_restored = AENetRsp.from_bytes(bytes_data[4:])
        self.assertEqual(rsp_restored.status, rsp.status)
        self.assertEqual(rsp_restored.request_id, rsp.request_id)

    def test_all_statuses(self):
        """测试所有状态类型"""
        for status in AENetRspStatus:
            rsp = AENetRsp(status=status)
            self.assertEqual(rsp.status, status.value)


class TestAENetErrorInfo(unittest.TestCase):
    """测试 AENetErrorInfo"""

    def test_create_error_info(self):
        """测试创建错误信息"""
        error = AENetErrorInfo(
            code="ERR_001",
            message="Test error",
            details={"key": "value"}
        )
        self.assertEqual(error.code, "ERR_001")
        self.assertEqual(error.message, "Test error")
        self.assertIsNotNone(error.details)

    def test_error_info_without_details(self):
        """测试不带详情的错误信息"""
        error = AENetErrorInfo(
            code="ERR_002",
            message="Simple error"
        )
        self.assertEqual(error.code, "ERR_002")
        self.assertIsNone(error.details)


class TestDataModels(unittest.TestCase):
    """测试数据模型"""

    def test_request_data(self):
        """测试请求数据模型"""
        data = AENetReqData(
            content="test content",
            parameters={"key": "value"}
        )
        self.assertEqual(data.content, "test content")
        self.assertIsNotNone(data.parameters)

    def test_response_data(self):
        """测试响应数据模型"""
        data = AENetRspData(
            content="response content",
            result={"key": "value"}
        )
        self.assertEqual(data.content, "response content")
        self.assertIsNotNone(data.result)


class TestValidation(unittest.TestCase):
    """测试数据验证"""

    def test_missing_required_field(self):
        """测试缺少必填字段"""
        with self.assertRaises(Exception):
            AENetReq()  # 缺少 action

    def test_invalid_enum_value(self):
        """测试无效的枚举值"""
        with self.assertRaises(Exception):
            json_str = '{"action": "invalid_action"}'
            AENetReq.model_validate_json(json_str)

    def test_valid_enum_string(self):
        """测试有效的枚举字符串值"""
        json_str = '{"action": "chat"}'
        req = AENetReq.model_validate_json(json_str)
        self.assertEqual(req.action, AENetReqAction.CHAT.value)


if __name__ == '__main__':
    unittest.main()
