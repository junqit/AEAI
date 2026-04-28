"""
请求处理器接口

定义网络层与业务层的交互协议
"""

from typing import Protocol
from ...Network.Core import AENetReq


class IRequestHandler(Protocol):
    """
    请求处理器接口

    业务层需要实现此接口来处理来自网络层的请求
    """

    def handle_request(self, request: AENetReq, connection_id: str) -> None:
        """
        处理接收到的请求

        Args:
            request: 请求对象
            connection_id: 连接ID，用于发送响应时指定目标
        """
        ...
