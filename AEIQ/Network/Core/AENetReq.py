"""
网络请求数据模型（对标 Client/CocoaPods/AENetworkEngine Request/AEReq/AENetReq.swift）

业务字段（cont / req / user）保持不变；to_map/from_map 同步 Swift 新线协议：
  {"header":{"type":0,"requestId":"...","path":"..."}, "cont":{...}, "user":{...}}

- header 为顶层键（对标 Swift toMap 的 dataMap["header"]，旧 req.headers 已废弃）
- type 为 Int（AENetMessageType: request=0），对标 Swift AENetMessageType: Int
- cont / user 作顶层参数承载（对标 Swift parameters 扁平合并）
"""
import json
from enum import IntEnum
from pydantic import BaseModel
from typing import Optional


class AENetMessageType(IntEnum):
    """消息类型标识（序列化到 header.type）。对标 Swift AENetMessageType: Int。"""
    REQUEST = 0   # 请求
    RESPONSE = 1  # 响应


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
    """请求信息（对应 Swift header.requestId / header.path + method）"""
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

    # ==================== Swift 线协议适配 ====================

    def to_map(self) -> dict:
        """对标 Swift AENetReq.toMap：header{type=REQUEST,requestId,path}；cont/user 作顶层参数。"""
        header = {"type": int(AENetMessageType.REQUEST)}
        if self.req:
            if self.req.requestId:
                header["requestId"] = self.req.requestId
            if self.req.path:
                header["path"] = self.req.path
        data_map = {"header": header}
        if self.cont is not None:
            data_map["cont"] = self.cont.model_dump(exclude_none=True)
        if self.user is not None:
            data_map["user"] = self.user.model_dump(exclude_none=True)
        return data_map

    @classmethod
    def from_map(cls, obj: dict) -> "AENetReq":
        """对标 Swift AENetReq.fromMap：从 header 取 requestId/path；cont/user 作顶层参数。"""
        header = obj.get("header") or {}
        request_id = header.get("requestId")
        path = header.get("path")
        method = "POST"  # Swift fromMap 固定 POST
        req_info = AENetReqInfo(requestId=request_id, path=path, method=method)

        cont = AENetCont.model_validate(obj["cont"]) if obj.get("cont") is not None else None
        user = AEUserInfo.model_validate(obj["user"]) if obj.get("user") is not None else None
        return cls(cont=cont, req=req_info, user=user)

    def to_bytes(self) -> bytes:
        return json.dumps(self.to_map(), ensure_ascii=False).encode('utf-8')

    @classmethod
    def from_bytes(cls, data: bytes) -> 'AENetReq':
        return cls.from_map(json.loads(data.decode('utf-8')))

    model_config = {"populate_by_name": True}
