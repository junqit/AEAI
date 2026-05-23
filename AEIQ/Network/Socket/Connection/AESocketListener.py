import logging
from ...Core import AENetReq

logger = logging.getLogger(__name__)


class AESocketListener:
    """
    Socket 数据监听器接口
    上层业务实现此接口接收请求
    """

    def on_request_received(self, request: AENetReq) -> None:
        raise NotImplementedError
