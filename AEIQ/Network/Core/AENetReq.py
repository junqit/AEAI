from pydantic import BaseModel, Field
from typing import Any, Optional, Dict


class AENetReqContext(BaseModel):
    """请求上下文"""
    type: Optional[str] = None
    ident: Optional[str] = None

class AENetReqInfo(BaseModel):
    """请求信息"""
    path: Optional[str] = None
    timeout: Optional[float] = None
    requestId: Optional[str] = None
    method: Optional[str] = None

class AENetReqUser(BaseModel):
    """用户信息"""
    uid: Optional[str] = None
    ident: Optional[str] = None

    @property
    def user_key(self) -> str:
        return f"{self.uid or ''}:{self.ident or ''}"

class AENetReqQuestion(BaseModel):
    """问题消息体"""
    type: Optional[int] = None
    ident: Optional[str] = None
    content: Optional[str] = None


class AENetReq(BaseModel):
    """网络请求数据"""
    cont: Optional[AENetReqContext] = None
    req: Optional[AENetReqInfo] = None
    user: Optional[AENetReqUser] = None
    question: Optional[AENetReqQuestion] = None

    def to_bytes(self) -> bytes:
        return self.model_dump_json(exclude_none=True).encode('utf-8')

    @classmethod
    def from_bytes(cls, data: bytes) -> 'AENetReq':
        return cls.model_validate_json(data.decode('utf-8'))

    model_config = {"populate_by_name": True}
