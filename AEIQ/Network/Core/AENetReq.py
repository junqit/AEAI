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


class AENetReq(BaseModel):
    """
    网络请求数据包装类

    用于封装通过 socket 发送的请求数据

    示例:
    {
        "action": "chat",
        "content": "用户输入的内容",
        "context": {"id": "ctx_xxx"},
        "question": {"type": "text", "content": "..."},
        "llm_types": ["claude", "gemini"],
        "request_id": "req_001"
    }
    """
    action: AENetReqAction = Field(..., description="请求动作类型")

    # 业务数据字段（直接展开，不再嵌套）
    content: Optional[str] = Field(None, description="请求内容")
    context: Optional[Dict[str, Any]] = Field(None, description="上下文信息")
    question: Optional[Dict[str, Any]] = Field(None, description="问题详情")
    llm_types: Optional[list] = Field(None, description="LLM 类型列表")

    # 其他可选字段
    parameters: Optional[Dict[str, Any]] = Field(None, description="额外参数")
    request_id: Optional[str] = Field(None, description="请求ID，用于追踪请求-响应")

    # 原始请求信息（保留用于调试）
    path: Optional[str] = Field(None, description="请求路径")
    method: Optional[str] = Field(None, description="请求方法")
    timeout: Optional[float] = Field(None, description="超时时间")

    def to_bytes(self) -> bytes:
        """
        将请求对象序列化为字节流（纯 JSON 数据，不含长度前缀）

        注意：长度信息已经在 AEPacket 的包头中，这里只返回 JSON 数据
        """
        json_str = self.model_dump_json()
        return json_str.encode('utf-8')

    @classmethod
    def from_bytes(cls, data: bytes) -> 'AENetReq':
        """
        从字节流反序列化请求对象（纯 JSON 数据）

        注意：传入的 data 是从 AEPacket 中提取的纯数据部分，不含包头
        """
        json_str = data.decode('utf-8')
        return cls.model_validate_json(json_str)

    model_config = {"use_enum_values": True}  # Pydantic v2 语法
