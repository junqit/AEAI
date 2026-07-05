from typing import Dict, Optional
import logging

from Network.Core import AENetReq, AENetRsp
from Network.Socket.Connection.AESocketListener import AESocketInterface
from ..UserContext.AEUserContext import AEUserContext

logger = logging.getLogger(__name__)


class AENetRouteCenter:
    """
    网络路由中心：实现 AESocketListener 接收 NetReq，按 user.user_key 命中/创建 AEUserContext 并转交；
    同时实现 AENetworkDelegate，为 AEUserContext 提供 NetReq/NetRsp 发送出口。
    LLM 请求与回程路由由各 AEUserContext 自行处理。
    """

    def __init__(self, socket_interface: Optional[AESocketInterface] = None):
        self._socket_interface = socket_interface
        # userKey -> AEUserContext：收到 NetReq 后按 user.user_key 命中/创建并存储
        self.userCenters: Dict[str, AEUserContext] = {}

    # ==================== AESocketListener 接口实现 ====================

    def on_request_received(self, request: AENetReq) -> None:
        """按 user.user_key 命中/创建 AEUserContext，转交请求。"""
        if not request.user:
            logger.warning("Request has no user info, ignored")
            return

        try:
            user_key = request.user.user_key
        except ValueError:
            logger.warning("Request user has no uid, ignored")
            return

        center = self.userCenters.get(user_key)
        if center is None:
            center = AEUserContext(request.user, self)
            self.userCenters[user_key] = center

        center.handle_request(request)

    # ==================== AENetworkDelegate 实现 ====================

    def send_request(self, request: AENetReq) -> None:
        """Context 需要发送 NetReq 时调用"""
        if self._socket_interface:
            self._socket_interface.send_request(request)

    def send_response(self, response: AENetRsp) -> None:
        """Context 需要发送 NetRsp 时调用"""
        if self._socket_interface:
            self._socket_interface.send_response(response)
