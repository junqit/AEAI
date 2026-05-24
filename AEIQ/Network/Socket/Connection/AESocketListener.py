import logging
from ...Core import AENetReq, AENetRsp

logger = logging.getLogger(__name__)


class AESocketInterface:
    """
    Socket 发送接口
    提供发送 Req 与 Rsp 的能力
    """

    def send_request(self, request: AENetReq) -> bool:
        raise NotImplementedError

    def send_response(self, response: AENetRsp) -> bool:
        raise NotImplementedError


class AESocketListener:
    """
    Socket 数据监听器接口
    上层业务实现此接口接收请求
    """

    def on_request_received(self, request: AENetReq) -> None:
        raise NotImplementedError
