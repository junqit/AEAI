"""
网络响应数据模型（对标 Client/CocoaPods/AENetworkEngine Request/AERsp/AENetRsp.swift）

业务字段（code / cont / req / rsp / user）保持不变；to_map/from_map 同步 Swift 新线协议：
  {"header":{"type":1,"requestId":"...","path":"..."}, "code":200, "cont":{...}, "rsp":{...}}

- header 为顶层键（对标 Swift toMap 的 dataMap["header"]，旧 req.headers 已废弃）
- type 为 Int（AENetMessageType: response=1）
- user 不上线（服务端路由用，对标 Swift AENetRsp 无 user 字段）
- path 回显请求路径（Python 扩展；Swift AENetRsp.fromMap 会保留于 rawData，不影响）
"""
import json
from enum import IntEnum
from pydantic import BaseModel
from typing import Optional, Dict, Any

from .AENetReq import AENetCont, AENetReqInfo, AEUserInfo, AENetMessageType


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

    # ==================== Swift 线协议适配 ====================

    def to_map(self) -> dict:
        """对标 Swift AENetRsp.toMap：header{type=RESPONSE,requestId[,path]}；code/cont/rsp 作顶层。
        user 不上线（服务端路由用）。path 回显请求路径（Python 扩展）。"""
        header = {"type": int(AENetMessageType.RESPONSE)}
        if self.req:
            if self.req.requestId:
                header["requestId"] = self.req.requestId
            if self.req.path:
                header["path"] = self.req.path

        data_map = {"header": header}
        data_map["code"] = int(self.code)
        if self.cont is not None:
            data_map["cont"] = self.cont.model_dump(exclude_none=True)
        if self.rsp is not None:
            data_map["rsp"] = self.rsp
        # user 不序列化（服务端用于路由，对标 Swift AENetRsp 无 user 字段）
        return data_map

    @classmethod
    def from_map(cls, obj: dict) -> "AENetRsp":
        """对标 Swift AENetRsp.fromMap：从 header 取 requestId/path；code/cont/rsp 作顶层。"""
        header = obj.get("header") or {}
        request_id = header.get("requestId")
        path = header.get("path")
        code = obj.get("code", AENetRspCode.success)

        cont = AENetCont.model_validate(obj["cont"]) if obj.get("cont") is not None else None
        rsp = obj.get("rsp")
        user = AEUserInfo.model_validate(obj["user"]) if obj.get("user") is not None else None
        req_info = AENetReqInfo(requestId=request_id, path=path) if (request_id or path) else None
        return cls(
            code=code,
            cont=cont,
            req=req_info,
            rsp=rsp,
            user=user,
        )

    def to_bytes(self) -> bytes:
        return json.dumps(self.to_map(), ensure_ascii=False).encode('utf-8')

    @classmethod
    def from_bytes(cls, data: bytes) -> 'AENetRsp':
        return cls.from_map(json.loads(data.decode('utf-8')))

    model_config = {"populate_by_name": True}
