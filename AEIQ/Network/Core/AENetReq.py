from pydantic import BaseModel, Field
from typing import Any, Optional, Dict


class AENetQues(BaseModel):
    """问题消息体"""
    type: Optional[int] = None
    ident: Optional[str] = None
    content: Optional[str] = None


class AENetCont(BaseModel):
    """请求上下文"""
    type: Optional[str] = None
    ident: Optional[str] = None
    space: Optional[str] = None
    ques: Optional[AENetQues] = None

class AENetReqInfo(BaseModel):
    """请求信息"""
    path: Optional[str] = None
    timeout: Optional[float] = None
    requestId: Optional[str] = None
    method: Optional[str] = None

class AEUserInfo(BaseModel):
    """用户信息"""
    uid: Optional[str] = None
    ident: Optional[str] = None

    @property
    def user_key(self) -> str:
        # 业务键暂仅使用 uid，ident 不参与业务
        uid = self.uid or ""
        if not uid:
            raise ValueError("user_key 为空：uid 未提供")
        return uid


class AENetReq(BaseModel):
    """网络请求数据"""
    cont: Optional[AENetCont] = None
    req: Optional[AENetReqInfo] = None
    user: Optional[AEUserInfo] = None

    def to_bytes(self) -> bytes:
        return self.model_dump_json(exclude_none=True).encode('utf-8')

    @classmethod
    def from_bytes(cls, data: bytes) -> 'AENetReq':
        return cls.model_validate_json(data.decode('utf-8'))

    model_config = {"populate_by_name": True}
