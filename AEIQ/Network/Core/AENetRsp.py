from pydantic import BaseModel, Field
from typing import Any, Optional, Dict
from enum import Enum


class AENetRspStatus(Enum):
    """响应状态类型"""
    SUCCESS = "success"  # 成功
    ERROR = "error"  # 错误
    TIMEOUT = "timeout"  # 超时
    INVALID = "invalid"  # 无效请求
    UNAUTHORIZED = "unauthorized"  # 未授权
    PROCESSING = "processing"  # 处理中


class AENetErrorInfo(BaseModel):
    """错误信息详情"""
    code: str = Field(..., description="错误码")
    message: str = Field(..., description="错误消息")
    details: Optional[Dict[str, Any]] = Field(None, description="错误详细信息")


class AENetRspData(BaseModel):
    """响应数据"""
    content: Optional[str] = None
    result: Optional[Dict[str, Any]] = None


class AENetRsp(BaseModel):
    """
    网络响应数据包装类

    用于封装通过 socket 接收的响应数据

    示例:
    {
        "status": "success",
        "data": {
            "content": "响应内容",
            "result": {"key": "value"}
        },
        "error": null,
        "request_id": "req_001"
    }

    错误响应示例:
    {
        "status": "error",
        "data": null,
        "error": {
            "code": "ERR_001",
            "message": "处理失败",
            "details": {"reason": "invalid input"}
        },
        "request_id": "req_001"
    }
    """
    status: AENetRspStatus = Field(..., description="响应状态")
    data: Optional[AENetRspData] = Field(None, description="响应数据")
    error: Optional[AENetErrorInfo] = Field(None, description="错误信息")
    request_id: Optional[str] = Field(None, description="对应的请求ID")

    model_config = {"use_enum_values": True}  # Pydantic v2 语法

    @property
    def is_success(self) -> bool:
        """判断响应是否成功"""
        return self.status == AENetRspStatus.SUCCESS.value

    @property
    def is_error(self) -> bool:
        """判断响应是否为错误"""
        return self.status == AENetRspStatus.ERROR.value

    def to_bytes(self) -> bytes:
        """
        将响应对象序列化为字节流
        格式: [数据长度(4字节)][JSON数据]
        """
        json_str = self.model_dump_json()
        json_bytes = json_str.encode('utf-8')
        # 使用4字节表示数据长度（大端序）
        length_bytes = len(json_bytes).to_bytes(4, byteorder='big')
        return length_bytes + json_bytes

    @classmethod
    def from_bytes(cls, data: bytes) -> 'AENetRsp':
        """
        从字节流反序列化响应对象
        """
        json_str = data.decode('utf-8')
        return cls.model_validate_json(json_str)

    @classmethod
    def create_success(cls, data: Optional[AENetRspData] = None, request_id: Optional[str] = None) -> 'AENetRsp':
        """
        创建成功响应

        Args:
            data: 响应数据
            request_id: 请求ID

        Returns:
            成功响应对象
        """
        return cls(status=AENetRspStatus.SUCCESS, data=data, request_id=request_id)

    @classmethod
    def create_error(cls, error_code: str, error_message: str,
                     error_details: Optional[Dict[str, Any]] = None,
                     request_id: Optional[str] = None) -> 'AENetRsp':
        """
        创建错误响应

        Args:
            error_code: 错误码
            error_message: 错误消息
            error_details: 错误详情
            request_id: 请求ID

        Returns:
            错误响应对象
        """
        error_info = AENetErrorInfo(
            code=error_code,
            message=error_message,
            details=error_details
        )
        return cls(status=AENetRspStatus.ERROR, error=error_info, request_id=request_id)
