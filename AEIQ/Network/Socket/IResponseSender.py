"""
响应发送器接口

定义业务层向网络层发送响应的协议
"""

from typing import Protocol
from ...Network.Core import AENetRsp


class IResponseSender(Protocol):
    """
    响应发送器接口

    网络层需要实现此接口，供业务层发送响应
    """

    def send_response(self, connection_id: str, response: AENetRsp) -> bool:
        """
        发送响应到指定连接

        Args:
            connection_id: 连接ID
            response: 响应对象

        Returns:
            是否发送成功
        """
        ...
