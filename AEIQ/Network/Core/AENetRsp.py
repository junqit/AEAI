from enum import IntEnum
from pydantic import BaseModel
from typing import Optional, Dict, Any

from .AENetReq import AENetCont, AENetReqInfo, AEUserInfo


class AENetRspCode(IntEnum):
    success = 200
    created = 201
    badRequest = 400
    unauthorized = 401
    forbidden = 403
    notFound = 404
    timeout = 408
    serverError = 500
    serviceUnavailable = 503
    unknown = -1


class AENetRspResult(BaseModel):
    """响应结果"""
    data: Optional[Dict[str, Any]] = None


class AENetRsp(BaseModel):
    """网络响应数据"""
    code: int = AENetRspCode.success
    cont: Optional[AENetCont] = None
    req: Optional[AENetReqInfo] = None
    rsp: Optional[Dict[str, Any]] = None
    user: Optional[AEUserInfo] = None

    def to_bytes(self) -> bytes:
        return self.model_dump_json(exclude_none=True, exclude={'user'}).encode('utf-8')

    @classmethod
    def from_bytes(cls, data: bytes) -> 'AENetRsp':
        return cls.model_validate_json(data.decode('utf-8'))

    model_config = {"populate_by_name": True}
