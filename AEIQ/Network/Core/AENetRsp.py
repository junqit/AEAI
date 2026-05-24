from pydantic import BaseModel
from typing import Optional

from .AENetReq import AENetReqContext, AENetReqInfo, AENetReqUser


class AENetRsp(BaseModel):
    """网络响应数据"""
    cont: Optional[AENetReqContext] = None
    rsp: Optional[AENetReqInfo] = None
    user: Optional[AENetReqUser] = None

    def to_bytes(self) -> bytes:
        return self.model_dump_json(exclude_none=True, exclude={'user'}).encode('utf-8')

    @classmethod
    def from_bytes(cls, data: bytes) -> 'AENetRsp':
        return cls.model_validate_json(data.decode('utf-8'))

    model_config = {"populate_by_name": True}
