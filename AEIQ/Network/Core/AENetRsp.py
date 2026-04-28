from pydantic import BaseModel, Field
from typing import Any, Optional, Dict


class AENetErrorInfo(BaseModel):
    """错误信息"""
    code: str
    message: str
    details: Optional[Dict[str, Any]] = None


class AENetRsp(BaseModel):
    """网络响应数据"""
    status: str
    content: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[AENetErrorInfo] = None
    requestId: Optional[str] = Field(None, alias="request_id")

    def to_bytes(self) -> bytes:
        return self.model_dump_json(by_alias=True, exclude_none=True).encode('utf-8')

    @classmethod
    def from_bytes(cls, data: bytes) -> 'AENetRsp':
        return cls.model_validate_json(data.decode('utf-8'))

    @classmethod
    def create_success(cls, requestId: Optional[str] = None,
                      content: Optional[str] = None,
                      result: Optional[Dict[str, Any]] = None) -> 'AENetRsp':
        return cls(status="success", content=content, result=result, requestId=requestId)

    @classmethod
    def create_error(cls, requestId: Optional[str] = None,
                     error_code: str = "ERR_UNKNOWN",
                     error_message: str = "",
                     error_details: Optional[Dict[str, Any]] = None) -> 'AENetRsp':
        return cls(
            status="error",
            error=AENetErrorInfo(code=error_code, message=error_message, details=error_details),
            requestId=requestId
        )

    model_config = {"populate_by_name": True}




