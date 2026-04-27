from typing import Callable, Optional
import socket
import threading
import logging
from ..Core import AENetReq, AENetRsp

logger = logging.getLogger(__name__)


class AESocketListener:
    """
    Socket 数据监听器接口
    用于回调接收到的数据
    """

    def on_request_received(self, request: AENetReq) -> None:
        """
        当接收到请求数据时的回调方法

        Args:
            request: 接收到的请求数据
        """
        raise NotImplementedError("子类必须实现 on_request_received 方法")

    def on_data_received(self, response: AENetRsp) -> None:
        """
        当接收到响应数据时的回调方法

        Args:
            response: 接收到的响应数据
        """
        raise NotImplementedError("子类必须实现 on_data_received 方法")

    def on_connection_closed(self) -> None:
        """
        当连接关闭时的回调方法
        """
        pass

    def on_error(self, error: Exception) -> None:
        """
        当发生错误时的回调方法

        Args:
            error: 发生的异常
        """
        logger.error(f"Socket error: {error}")
