from pydantic import BaseModel, Field
from typing import Any, Optional, Dict
from enum import Enum


class AENetReqAction(Enum):
    """网络请求动作类型"""
    CHAT = "chat"  # 聊天请求
    QUERY = "query"  # 查询请求
    COMMAND = "command"  # 命令请求
    HEARTBEAT = "heartbeat"  # 心跳
    CLOSE = "close"  # 关闭连接
    CUSTOM = "custom"  # 自定义动作


class AENetReqData(BaseModel):
    """请求数据"""
    content: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None


class AENetReq(BaseModel):
    """
    网络请求数据包装类

    用于封装通过 socket 发送的请求数据

    示例:
    {
        "action": "chat",
        "data": {
            "content": "用户输入的内容",
            "parameters": {"key": "value"}
        },
        "request_id": "req_001"
    }
    """
    action: AENetReqAction = Field(..., description="请求动作类型")
    data: Optional[AENetReqData] = Field(None, description="请求数据")
    request_id: Optional[str] = Field(None, description="请求ID，用于追踪请求-响应")

    def to_bytes(self) -> bytes:
        """
        将请求对象序列化为字节流
        格式: [数据长度(4字节)][JSON数据]
        """
        json_str = self.model_dump_json()
        json_bytes = json_str.encode('utf-8')
        # 使用4字节表示数据长度（大端序）
        length_bytes = len(json_bytes).to_bytes(4, byteorder='big')
        return length_bytes + json_bytes

    @classmethod
    def from_bytes(cls, data: bytes) -> 'AENetReq':
        """
        从字节流反序列化请求对象
        """
        json_str = data.decode('utf-8')
        return cls.model_validate_json(json_str)

    model_config = {"use_enum_values": True}  # Pydantic v2 语法
